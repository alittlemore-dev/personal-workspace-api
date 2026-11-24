import asyncio
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.finance.assets.analytics_use_cases import AssetAnalyticsUseCase
from core.finance.assets.enums import AssetMovementKind as Kind
from core.finance.assets.enums import AssetPositionKind, AssetSource
from core.finance.assets.exceptions import AssetPermissionError
from core.finance.assets.reports import AssetReportParams
from core.finance.assets.schemas import (
    AssetLocationDraft,
    AssetMovement,
    AssetMovementCommand,
    AssetMovementDeletion,
    AssetMovementsParams,
    AssetMovementUpdate,
    AssetOpeningPreviewParams,
    AssetPosition,
    AssetPositionDraft,
    CreateOverviewAsset,
)
from core.finance.assets.services import AssetMovementService
from core.finance.assets.valuation import AssetValuationParams
from core.finance.enums import FinanceCurrency, FinanceKind
from core.finance.exceptions import (
    FinanceConflictError,
    FinanceNotFoundError,
    FinanceRateUnavailableError,
    InvalidFinanceDataError,
)
from core.finance.schemas import (
    Amount,
    CreateFinanceTransactionParams,
    DeleteFinanceCategoryParams,
    EnsureFinanceMonthParams,
    FinanceActor,
    SetFinanceTransactionDeletedParams,
    UpdateOpeningBalanceParams,
)
from core.i18n.enums import LanguageEnum
from infra.postgresql.models.finance import (
    FinanceMonthModel,
    FinanceTrackerModel,
    FinanceTransactionModel,
)
from infra.postgresql.models.finance_assets import AssetMovementModel, AssetMovementRevisionModel
from infra.postgresql.models.finance_notifications import FinanceEventModel
from infra.postgresql.storages.finance import FinanceDatabaseStorage
from infra.postgresql.storages.finance_asset_analytics import FinanceAssetAnalyticsStorage
from infra.postgresql.storages.finance_assets import AssetDatabaseStorage
from tests.helpers.factories.finance_assets import FinanceAssetFactory as Factory
from tests.test_cases import StorageTestCase


class TestFinanceAssets(StorageTestCase):
    now = datetime(2026, 3, 31, 12, tzinfo=UTC)
    owner = "journal-owner"

    def service(self, session: AsyncSession) -> AssetMovementService:
        finance = self.factory.core.finance_use_case(FinanceDatabaseStorage(session=session))
        return AssetMovementService(
            storage=AssetDatabaseStorage(session=session),
            finance=finance.storage,
            months=finance.months,
            rate_client=finance.rate_client,
            events=finance.events,
        )

    @pytest_asyncio.fixture(autouse=True)
    async def prepare(self) -> None:
        self.journal = self.service(self.db_session)
        self.budget = self.factory.core.finance_use_case(self.journal.finance)
        await self.factory.db.seed_finance_templates(self.db_session)
        self.ensure = EnsureFinanceMonthParams(
            owner_username=self.owner,
            time_zone=ZoneInfo("UTC"),
            language=LanguageEnum.RU,
            now=self.now,
        )
        await self.budget.ensure_month(self.ensure)
        await self.journal.finance.save_rate_set(
            rate_set=self.factory.core.finance_rate_set(self.now.date()),
        )
        self.location = await self.journal.create_location(
            owner_username=self.owner,
            draft=AssetLocationDraft(name="Broker"),
        )
        self.cash = await self.position(AssetPositionKind.BROKER_CASH)

    async def position(self, kind: AssetPositionKind) -> AssetPosition:
        return await self.journal.create_position(
            owner_username=self.owner,
            draft=AssetPositionDraft(
                location_id=self.location.id,
                name=kind.value,
                kind=kind,
                currency=FinanceCurrency.RUB,
                instrument="BLUE" if kind.security else "",
                venue="XYZ" if kind.security else "",
                annual_rate=None,
                matures_on=None,
            ),
        )

    def command(
        self,
        kind: Kind,
        amount: int | None = None,
        position: str | None = None,
        *,
        quantity: int | None = None,
        counter: str | None = None,
    ) -> AssetMovementCommand:
        movement = Factory.movement(
            kind,
            self.now.date(),
            position or self.cash.id,
            amount=amount if kind != Kind.VALUATION else None,
            quantity=quantity,
            counter=counter,
            total_value=amount if kind == Kind.VALUATION else None,
        )
        return AssetMovementCommand(
            owner_username=self.owner,
            source=AssetSource.PAT,
            can_write_budget=True,
            now=self.now,
            request_id=uuid4(),
            draft=movement.draft,
        )

    def deletion(self, movement: AssetMovement, *, deleted: bool) -> AssetMovementDeletion:
        return AssetMovementDeletion(
            owner_username=self.owner,
            source=AssetSource.WEB,
            can_write_budget=True,
            now=self.now,
            movement_id=movement.id,
            version=movement.version,
            deleted=deleted,
        )

    async def test_salary_trade_return_and_late_carry_adjustment(self) -> None:
        month = await self.journal.finance.get_month(owner_username=self.owner, now=self.now)
        salary = next(c for c in month.categories if c.kind == FinanceKind.INCOME)
        await self.budget.create_transaction(
            CreateFinanceTransactionParams(
                owner_username=self.owner,
                now=self.now,
                period_start=None,
                actor=FinanceActor.web(self.owner),
                draft=self.factory.core.finance_transaction_draft(
                    category_id=salary.id,
                    amount="100000",
                    currency=FinanceCurrency.RUB,
                    occurred_at=self.now,
                ),
            ),
        )
        stock = await self.position(AssetPositionKind.STOCK)
        await self.journal.apply(self.command(Kind.CONTRIBUTION, 10000))
        trade = await self.journal.apply(
            self.command(Kind.BUY, 6000, stock.id, quantity=3, counter=self.cash.id),
        )
        await self.journal.apply(self.command(Kind.VALUATION, 6500, stock.id))
        await self.journal.apply(self.command(Kind.WITHDRAWAL, 4000))
        month = await self.journal.finance.get_month(owner_username=self.owner, now=self.now)
        flows = month.transfers[month.currency]
        assert (month.closing_balance, month.actual_expense, month.income_minus_expenses) == (
            Amount(94000),
            Amount(0),
            Amount(100000),
        )
        assert flows.contributions - flows.withdrawals == 6000
        assert trade.draft.quantity == 3
        april = datetime(2026, 4, 2, tzinfo=UTC)
        following = await self.budget.ensure_month(replace(self.ensure, now=april))
        assert following.opening_balance == 94000
        # A subsequently discovered March payout funded the late return.
        await self.journal.apply(replace(self.command(Kind.PAYOUT, 250), now=april))
        late = replace(self.command(Kind.WITHDRAWAL, 250), now=april)
        returned = await self.journal.apply(late)
        following = await self.journal.finance.get_month(owner_username=self.owner, now=april)
        assert (following.opening_balance, following.carry_correction) == (
            Amount(94000),
            Amount(250),
        )
        corrected = await self.budget.update_opening_balance(
            UpdateOpeningBalanceParams(owner_username=self.owner, now=april, amount=Amount(94250)),
        )
        assert corrected.carry_correction is None
        manual = await self.budget.update_opening_balance(
            UpdateOpeningBalanceParams(owner_username=self.owner, now=april, amount=Amount(94300)),
        )
        assert manual.carry_correction is None
        await self.journal.set_deleted(replace(self.deletion(returned, deleted=True), now=april))
        following = await self.journal.finance.get_month(owner_username=self.owner, now=april)
        assert following.opening_balance == 94300
        assert following.carry_correction == -250
        accepted = await self.budget.update_opening_balance(
            UpdateOpeningBalanceParams(owner_username=self.owner, now=april, amount=Amount(94050)),
        )
        assert accepted.carry_correction is None
        assert (
            await self.db_session.scalar(
                select(FinanceMonthModel.transferred_balance).where(
                    FinanceMonthModel.id == accepted.id,
                ),
            )
            == 94000
        )

    async def test_manual_bank_balances_and_budget_rollover_are_independent(self) -> None:
        await self.budget.update_opening_balance(
            UpdateOpeningBalanceParams(
                owner_username=self.owner,
                now=self.now,
                amount=Amount(400000),
            ),
        )
        bank = await self.position(AssetPositionKind.BANK)
        analytics = AssetAnalyticsUseCase(
            journal=self.journal.storage,
            storage=FinanceAssetAnalyticsStorage(session=self.db_session),
        )
        march = AssetReportParams(
            owner_username=self.owner,
            start=date(2026, 3, 1),
            end=self.now.date(),
            now=self.now,
            currency=FinanceCurrency.RUB,
        )
        assert (await analytics.report(march)).closing.known_value == 0
        await self.journal.apply(self.command(Kind.RECONCILE, 12000, bank.id))
        assert (await analytics.report(march)).closing.known_value == 12000

        april = datetime(2026, 4, 2, tzinfo=UTC)
        rolled = await self.budget.ensure_month(replace(self.ensure, now=april))
        assert rolled.opening_balance == 400000
        query = replace(march, start=date(2026, 4, 1), end=april.date(), now=april)
        carried = await analytics.report(query)
        assert carried.closing.known_value == 12000
        assert carried.forecast.start_value == 12000
        movements = await self.journal.storage.list_movements(
            owner_username=self.owner,
            end=april.date(),
        )
        assert [row.draft.kind for row in movements] == [Kind.RECONCILE]

        correction = self.command(Kind.RECONCILE, 17000, bank.id)
        await self.journal.apply(
            replace(correction, draft=replace(correction.draft, on_date=april.date()), now=april),
        )
        updated = await analytics.report(query)
        assert updated.closing.known_value == 17000
        assert updated.reconciliation == 5000
        assert updated.net_savings == 0
        assert updated.forecast.start_value == 17000
        assert (await analytics.report(march)).closing.known_value == 12000
        budget = await self.journal.finance.get_month(owner_username=self.owner, now=april)
        assert budget.closing_balance == 400000
        assert budget.actual_income == 0

    def overview_command(self) -> CreateOverviewAsset:
        return CreateOverviewAsset(
            owner_username=self.owner,
            now=self.now,
            source=AssetSource.WEB,
            can_write_budget=False,
            request_id=uuid4(),
            on_date=self.now.date(),
            amount=Decimal(12000),
            default_location_name="My accounts",
            position=AssetPositionDraft(
                name="Savings",
                kind=AssetPositionKind.SAVINGS,
                location_id="",
                currency=FinanceCurrency.RUB,
                instrument="",
                venue="",
                annual_rate=None,
                matures_on=None,
            ),
        )

    async def test_overview_add_is_atomic_and_retries_reuse_the_position_and_balance(self) -> None:
        command = self.overview_command()
        with pytest.raises(InvalidFinanceDataError):
            async with self.db_session.begin_nested():
                await self.journal.create_overview_asset(replace(command, amount=Decimal(-1)))
        assert await self.journal.storage.list_locations(owner_username=self.owner) == [
            self.location,
        ]
        assert await self.journal.storage.list_positions(owner_username=self.owner) == [self.cash]
        position = await self.journal.create_overview_asset(command)
        assert await self.journal.create_overview_asset(command) == position
        with pytest.raises(FinanceConflictError):
            await self.journal.create_overview_asset(replace(command, amount=Decimal(1000)))
        other = await self.journal.create_overview_asset(
            replace(
                command,
                request_id=uuid4(),
                amount=None,
                position=replace(command.position, name="Other"),
            ),
        )
        assert other.id != position.id
        assert other.location_id == position.location_id != self.location.id
        movements = await self.journal.storage.list_movements(owner_username=self.owner, end=None)
        assert [(row.draft.position_id, row.draft.amount, row.draft.kind) for row in movements] == [
            (position.id, Decimal(12000), Kind.OPENING_EXTERNAL),
        ]
        budget = await self.journal.finance.get_month(owner_username=self.owner, now=self.now)
        assert budget.closing_balance == 0
        assert budget.actual_income == 0

    async def test_asset_lifecycle_is_owner_scoped_and_keeps_the_history(self) -> None:
        command = self.overview_command()
        position = await self.journal.create_overview_asset(command)
        other = "another-owner"
        await self.budget.ensure_month(replace(self.ensure, owner_username=other))
        with pytest.raises(FinanceNotFoundError):
            await self.journal.create_overview_asset(
                replace(
                    command,
                    owner_username=other,
                    position=replace(command.position, location_id=position.location_id),
                ),
            )
        with pytest.raises(FinanceNotFoundError):
            await self.journal.archive_position(
                owner_username=other,
                position_id=position.id,
                archived=True,
            )
        with pytest.raises(FinanceNotFoundError):
            await self.journal.delete_position(owner_username=other, position_id=position.id)
        same_request = await self.journal.create_overview_asset(
            replace(command, owner_username=other),
        )
        assert same_request.id != position.id
        archive = await self.journal.archive_position(
            owner_username=self.owner,
            position_id=position.id,
            archived=True,
        )
        assert archive.archived
        with pytest.raises(FinanceConflictError):
            await self.journal.update_position(
                owner_username=self.owner,
                position_id=position.id,
                draft=replace(command.position, location_id=position.location_id, name="Renamed"),
            )
        delta = replace(
            self.command(Kind.DEPOSIT_EXTERNAL, 200, position.id),
            can_write_budget=False,
        )
        with pytest.raises(FinanceConflictError):
            await self.journal.apply(delta)
        with pytest.raises(FinanceConflictError):
            await self.journal.delete_position(owner_username=self.owner, position_id=position.id)
        [movement] = await self.journal.storage.list_movements(owner_username=self.owner, end=None)
        assert movement.draft.amount == 12000
        assert movement.draft.position_id == position.id
        restored = await self.journal.archive_position(
            owner_username=self.owner,
            position_id=position.id,
            archived=False,
        )
        assert not restored.archived
        assert (await self.journal.apply(delta)).draft.amount == 200
        await self.journal.delete_position(owner_username=self.owner, position_id=self.cash.id)
        assert await self.journal.storage.list_positions(owner_username=self.owner) == [restored]

    async def test_a_position_referenced_only_by_an_old_revision_cannot_be_removed(self) -> None:
        prior = await self.position(AssetPositionKind.SAVINGS)
        entry = await self.journal.apply(self.command(Kind.DEPOSIT_EXTERNAL, 100, prior.id))
        moved = await self.journal.update_movement(
            AssetMovementUpdate(
                owner_username=self.owner,
                source=AssetSource.WEB,
                can_write_budget=False,
                now=self.now,
                movement_id=entry.id,
                version=entry.version,
                draft=replace(entry.draft, position_id=self.cash.id),
            ),
        )
        assert moved.draft.position_id == self.cash.id
        with pytest.raises(FinanceConflictError):
            await self.journal.delete_position(owner_username=self.owner, position_id=prior.id)
        revisions = await self.journal.storage.revisions(
            owner_username=self.owner,
            movement_id=entry.id,
        )
        assert [r.draft.position_id for r in revisions] == [prior.id, self.cash.id]

    async def test_first_external_deposit_can_fund_a_transfer_later_that_day(self) -> None:
        destination = await self.position(AssetPositionKind.BANK)
        await self.journal.apply(
            replace(
                self.command(Kind.DEPOSIT_EXTERNAL, 1000),
                can_write_budget=False,
            ),
        )
        await self.journal.apply(
            replace(
                self.command(Kind.TRANSFER, 350, counter=destination.id),
                now=self.now + timedelta(minutes=5),
                can_write_budget=False,
            ),
        )
        analytics = AssetAnalyticsUseCase(
            journal=self.journal.storage,
            storage=FinanceAssetAnalyticsStorage(session=self.db_session),
        )
        report = await analytics.report(
            AssetReportParams(
                owner_username=self.owner,
                start=self.now.date(),
                end=self.now.date(),
                now=self.now + timedelta(minutes=10),
                currency=FinanceCurrency.RUB,
            ),
        )
        assert report.deposits == report.net_savings == report.closing.known_value == 1000
        assert {row.id: row.value for row in report.closing.positions} == {
            self.cash.id: Decimal(650),
            destination.id: Decimal(350),
        }

    async def test_foreign_currency_deposits_and_withdrawals_keep_entered_amount_and_snapshot(
        self,
    ) -> None:
        command = self.command(Kind.DEPOSIT_EXTERNAL)
        deposit = replace(
            command,
            can_write_budget=False,
            draft=replace(
                command.draft,
                entered_amount=Decimal("10.50"),
                entered_currency=FinanceCurrency.USD,
            ),
        )
        created = await self.journal.apply(deposit)
        assert created.draft.amount == Decimal(840)
        assert created.rate_set_id is not None
        assert await self.journal.apply(deposit) == created
        different = replace(deposit.draft, entered_currency=FinanceCurrency.EUR)
        with pytest.raises(FinanceConflictError):
            await self.journal.apply(replace(deposit, draft=different))
        rates = self.factory.core.finance_rate_set(self.now.date())
        new_rate = await self.journal.finance.save_rate_set(
            rate_set=replace(
                rates,
                fetched_at=self.now,
                payload_hash="later-publication",
                rates={**rates.rates, FinanceCurrency.USD: Decimal("81.345")},
            ),
        )
        corrected = await self.journal.update_movement(
            AssetMovementUpdate(
                owner_username=self.owner,
                source=AssetSource.WEB,
                can_write_budget=False,
                now=self.now,
                movement_id=created.id,
                version=created.version,
                draft=replace(deposit.draft, entered_amount=Decimal(12)),
            ),
        )
        assert corrected.rate_set_id == created.rate_set_id
        assert corrected.draft.amount == Decimal(960)
        assert await self.journal.apply(deposit) == created
        take = self.command(Kind.WITHDRAW_EXTERNAL)
        withdrawal = await self.journal.apply(
            replace(
                take,
                draft=replace(
                    take.draft,
                    entered_currency=FinanceCurrency.USD,
                    entered_amount=Decimal(1),
                ),
            ),
        )
        assert withdrawal.rate_set_id == new_rate
        assert withdrawal.draft.amount == Decimal("81.35")
        analytics = AssetAnalyticsUseCase(
            journal=self.journal.storage,
            storage=FinanceAssetAnalyticsStorage(session=self.db_session),
        )
        query = AssetReportParams(
            owner_username=self.owner,
            start=self.now.date(),
            end=self.now.date(),
            now=self.now,
            currency=FinanceCurrency.RUB,
        )
        deleted = await self.journal.set_deleted(self.deletion(withdrawal, deleted=True))
        assert (await analytics.report(query)).closing.known_value == Decimal(960)
        await self.journal.set_deleted(self.deletion(deleted, deleted=False))
        report = await analytics.report(query)
        assert report.closing.known_value == report.net_savings == Decimal("878.65")
        month = await self.journal.finance.get_month(owner_username=self.owner, now=self.now)
        assert month.closing_balance == 0
        revisions = await self.journal.storage.revisions(
            owner_username=self.owner,
            movement_id=created.id,
        )
        assert [
            (r.draft.entered_currency, r.draft.entered_amount, r.draft.amount) for r in revisions
        ] == [
            (FinanceCurrency.USD, Decimal("10.5"), Decimal(840)),
            (FinanceCurrency.USD, Decimal(12), Decimal(960)),
        ]
        with pytest.raises(FinanceConflictError):
            await self.journal.apply(
                replace(
                    take,
                    request_id=uuid4(),
                    draft=replace(
                        take.draft,
                        entered_currency=FinanceCurrency.USD,
                        entered_amount=Decimal(12),
                    ),
                ),
            )

    async def test_reads_asset_amounts_and_revisions_written_before_entered_currency(self) -> None:
        command = self.command(Kind.DEPOSIT_EXTERNAL, 35)
        old = await self.journal.apply(command)
        for model, snapshot, path in (
            (AssetMovementModel, AssetMovementModel.draft, ["value"]),
            (AssetMovementRevisionModel, AssetMovementRevisionModel.snapshot, ["value", "draft"]),
        ):
            without_amount = snapshot.op("#-")(array([*path, "entered_amount"]))
            without_pair = without_amount.op("#-")(array([*path, "entered_currency"]))
            await self.db_session.execute(
                update(model)
                .values({snapshot: without_pair})
                .execution_options(synchronize_session=False),
            )
        loaded = await self.journal.storage.get_movement(
            owner_username=self.owner,
            movement_id=old.id,
        )
        assert loaded.draft == command.draft
        assert await self.journal.apply(command) == old

    async def test_changing_date_uses_its_rate_or_leaves_the_previous_revision_intact(self) -> None:
        command = self.command(Kind.DEPOSIT_EXTERNAL)
        draft = replace(
            command.draft,
            entered_currency=FinanceCurrency.EUR,
            entered_amount=Decimal(5),
        )
        movement = await self.journal.apply(replace(command, draft=draft))
        previous_day = date(2026, 3, 29)
        edit = AssetMovementUpdate(
            owner_username=self.owner,
            now=self.now,
            source=AssetSource.WEB,
            can_write_budget=False,
            movement_id=movement.id,
            version=movement.version,
            draft=replace(draft, on_date=previous_day),
        )
        with pytest.raises(FinanceRateUnavailableError):
            await self.journal.update_movement(edit)
        stored = await self.journal.storage.get_movement(
            owner_username=self.owner,
            movement_id=movement.id,
        )
        assert stored == movement
        prior = self.factory.core.finance_rate_set(previous_day)
        rate_id = await self.journal.finance.save_rate_set(
            rate_set=replace(prior, rates={**prior.rates, FinanceCurrency.EUR: Decimal(87)}),
        )
        changed = await self.journal.update_movement(edit)
        assert changed.rate_set_id == rate_id != movement.rate_set_id
        assert changed.draft.amount == Decimal(435)

    async def test_external_movements_after_same_day_balance_edit_keep_budget_and_history(
        self,
    ) -> None:
        await self.budget.update_opening_balance(
            UpdateOpeningBalanceParams(
                owner_username=self.owner,
                now=self.now,
                amount=Amount(400000),
            ),
        )
        analytics = AssetAnalyticsUseCase(
            journal=self.journal.storage,
            storage=FinanceAssetAnalyticsStorage(session=self.db_session),
        )
        query = AssetReportParams(
            owner_username=self.owner,
            start=self.now.date().replace(day=1),
            end=self.now.date(),
            now=self.now,
            currency=FinanceCurrency.RUB,
        )
        observation = await self.journal.apply(
            replace(self.command(Kind.RECONCILE, 12000), can_write_budget=False),
        )
        deposit = await self.journal.apply(
            replace(
                self.command(Kind.DEPOSIT_EXTERNAL, 1500),
                can_write_budget=False,
                now=self.now + timedelta(minutes=1),
            ),
        )
        withdrawal = await self.journal.apply(
            replace(
                self.command(Kind.WITHDRAW_EXTERNAL, 300),
                can_write_budget=False,
                now=self.now + timedelta(minutes=2),
            ),
        )
        report = await analytics.report(query)
        assert (
            report.closing.known_value,
            report.deposits,
            report.withdrawals,
            report.net_savings,
        ) == (Decimal(13200), Decimal(1500), Decimal(300), Decimal(1200))
        updated = AssetMovementUpdate(
            owner_username=self.owner,
            now=self.now + timedelta(minutes=3),
            source=AssetSource.WEB,
            can_write_budget=False,
            movement_id=deposit.id,
            version=deposit.version,
            draft=replace(deposit.draft, amount=Decimal(800)),
        )
        await self.journal.update_movement(updated)
        assert (await analytics.report(query)).closing.known_value == 12500
        deleted = await self.journal.set_deleted(
            replace(self.deletion(withdrawal, deleted=True), can_write_budget=False),
        )
        assert (await analytics.report(query)).closing.known_value == 12800
        await self.journal.set_deleted(
            replace(self.deletion(deleted, deleted=False), can_write_budget=False),
        )
        assert (await analytics.report(query)).closing.known_value == 12500
        await self.journal.update_movement(
            replace(
                updated,
                movement_id=observation.id,
                version=observation.version,
                now=self.now + timedelta(minutes=5),
                draft=replace(observation.draft, amount=Decimal(13000)),
            ),
        )
        assert (await analytics.report(query)).closing.known_value == 13000
        await self.journal.apply(
            replace(
                self.command(Kind.DEPOSIT_EXTERNAL, 100),
                can_write_budget=False,
                now=self.now + timedelta(minutes=6),
            ),
        )
        report = await analytics.report(query)
        assert (report.closing.known_value, report.net_savings) == (Decimal(13100), Decimal(600))
        revisions = await self.journal.storage.revisions(
            owner_username=self.owner,
            movement_id=withdrawal.id,
        )
        assert [(row.version, row.deleted) for row in revisions] == [
            (1, False),
            (2, True),
            (3, False),
        ]
        budget = await self.journal.finance.get_month(owner_username=self.owner, now=self.now)
        assert (budget.closing_balance, budget.actual_income, budget.actual_expense) == (
            Amount(400000),
            Amount(0),
            Amount(0),
        )
        assert all(
            flow.contributions == flow.withdrawals == 0 for flow in budget.transfers.values()
        )

    async def test_income_follows_local_report_dates_after_a_move_across_month_boundary(
        self,
    ) -> None:
        await self.journal.apply(self.command(Kind.OPENING_EXTERNAL, 50))
        yerevan = ZoneInfo("Asia/Yerevan")
        earned_at = datetime(2026, 4, 1, 0, 30, tzinfo=yerevan)
        april = datetime(2026, 4, 2, tzinfo=UTC)
        month = await self.budget.ensure_month(replace(self.ensure, now=april, time_zone=yerevan))
        salary = next(c for c in month.categories if c.kind == FinanceKind.INCOME)
        await self.journal.finance.save_rate_set(
            rate_set=self.factory.core.finance_rate_set(earned_at.date()),
        )
        await self.budget.create_transaction(
            CreateFinanceTransactionParams(
                owner_username=self.owner,
                now=april,
                period_start=None,
                actor=FinanceActor.web(self.owner),
                draft=self.factory.core.finance_transaction_draft(
                    category_id=salary.id,
                    amount="100",
                    currency=FinanceCurrency.RUB,
                    occurred_at=earned_at,
                ),
            ),
        )
        analytics = AssetAnalyticsUseCase(
            journal=self.journal.storage,
            storage=FinanceAssetAnalyticsStorage(session=self.db_session),
        )
        march_report = AssetReportParams(
            owner_username=self.owner,
            start=date(2026, 3, 31),
            end=date(2026, 3, 31),
            currency=FinanceCurrency.RUB,
            now=april,
        )
        april_report = replace(march_report, start=earned_at.date(), end=earned_at.date())
        assert (await analytics.report(march_report)).income == 0
        assert (await analytics.report(april_report)).income == 100
        current = await self.budget.ensure_month(replace(self.ensure, now=april))
        assert current.actual_income == 100
        assert (await analytics.report(march_report)).income == 100
        assert (await analytics.report(april_report)).income == 0

    @pytest.mark.parametrize(
        ("kind", "opening"),
        [(Kind.OPENING_EXTERNAL, 100000), (Kind.OPENING_BUDGET, 400000)],
    )
    async def test_initial_allocation_and_statement_history(self, kind: Kind, opening: int) -> None:
        await self.budget.update_opening_balance(
            UpdateOpeningBalanceParams(
                owner_username=self.owner,
                now=self.now,
                amount=Amount(opening),
            ),
        )
        deposit = await self.position(AssetPositionKind.DEPOSIT)
        past = self.command(Kind.STATEMENT, 80000, deposit.id)
        await self.journal.apply(replace(past, draft=replace(past.draft, on_date=date(2024, 7, 1))))
        command = self.command(kind, 300000, deposit.id)
        await self.journal.apply(command)
        month = await self.journal.finance.get_month(owner_username=self.owner, now=self.now)
        assert month.closing_balance == 100000
        assert sum(flow.contributions for flow in month.transfers.values()) == 0
        past_rows = await self.journal.storage.list_movements(
            owner_username=self.owner,
            end=date(2024, 12, 31),
        )
        assert [m.draft.kind for m in past_rows] == [Kind.STATEMENT]
        assert await self.journal.storage.list_positions(owner_username="other") == []
        with pytest.raises(FinanceNotFoundError):
            await self.journal.storage.get_position(owner_username="other", position_id=deposit.id)
        assert (
            await self.db_session.scalar(select(func.count()).select_from(FinanceTrackerModel)) == 1
        )

    async def test_external_trades_update_holdings_and_savings_without_cash_postings(self) -> None:
        stock = await self.position(AssetPositionKind.STOCK)
        buy = self.command(Kind.BUY, 240, stock.id, quantity=4)
        sell = self.command(Kind.SELL, 80, stock.id, quantity=1)
        with pytest.raises(InvalidFinanceDataError):
            await self.journal.apply(buy)
        with pytest.raises(InvalidFinanceDataError):
            await self.journal.apply(
                replace(
                    buy,
                    draft=replace(buy.draft, external_funds=True, counter_position_id=self.cash.id),
                ),
            )
        buy = replace(buy, draft=replace(buy.draft, external_funds=True), can_write_budget=False)
        sell = replace(
            sell,
            draft=replace(sell.draft, external_funds=True),
            now=self.now + timedelta(minutes=1),
            can_write_budget=False,
        )
        purchased = await self.journal.apply(buy)
        assert purchased == await self.journal.apply(buy)
        sold = await self.journal.apply(sell)
        assert purchased.rate_set_id
        assert sold.rate_set_id
        analytics = AssetAnalyticsUseCase(
            journal=self.journal.storage,
            storage=FinanceAssetAnalyticsStorage(session=self.db_session),
        )
        period = AssetReportParams(
            owner_username=self.owner,
            start=self.now.date().replace(day=1),
            end=self.now.date(),
            now=sell.now,
            currency=FinanceCurrency.RUB,
        )
        report = await analytics.report(period)
        holding = next(p for p in report.closing.positions if p.id == stock.id)
        assert holding.quantity == 3
        assert holding.original_value == 240
        assert report.net_savings == 160
        assert report.revaluation == 80
        month = await self.journal.finance.get_month(owner_username=self.owner, now=self.now)
        assert month.closing_balance == 0
        assert not month.transfers
        await self.journal.set_deleted(self.deletion(sold, deleted=True))
        assert (await analytics.report(period)).net_savings == 240

    async def test_trade_after_value_only_observation_requires_existing_unit_count(self) -> None:
        stock = await self.position(AssetPositionKind.FUND)
        await self.journal.apply(self.command(Kind.OPENING_EXTERNAL, 100))
        await self.journal.apply(self.command(Kind.VALUATION, 100, stock.id))
        buy = self.command(Kind.BUY, 40, stock.id, quantity=2)
        buy = replace(
            buy,
            draft=replace(buy.draft, external_funds=True),
            now=self.now + timedelta(minutes=2),
        )
        with pytest.raises(FinanceConflictError):
            await self.journal.apply(buy)
        funded = self.command(Kind.BUY, 40, stock.id, quantity=2, counter=self.cash.id)
        with pytest.raises(FinanceConflictError):
            await self.journal.apply(replace(funded, now=buy.now))
        observation = self.command(Kind.RECONCILE, position=stock.id, quantity=5)
        await self.journal.apply(replace(observation, now=self.now + timedelta(minutes=1)))
        await self.journal.apply(buy)
        analytics = AssetAnalyticsUseCase(
            journal=self.journal.storage,
            storage=FinanceAssetAnalyticsStorage(session=self.db_session),
        )
        portfolio = await analytics.positions(
            AssetValuationParams(
                owner_username=self.owner,
                as_of=self.now.date(),
                currency=FinanceCurrency.RUB,
            ),
        )
        holding = next(p for p in portfolio.positions if p.id == stock.id)
        assert holding.quantity == 7
        assert holding.original_value == 140

    async def test_direct_buy_and_group_version_permissions_and_replay(self) -> None:
        stock = await self.position(AssetPositionKind.FUND)
        command = self.command(Kind.BUY_FROM_BUDGET, 500, stock.id, quantity=5)
        with pytest.raises(AssetPermissionError):
            await self.journal.apply(replace(command, can_write_budget=False))
        movement = await self.journal.apply(command)
        assert movement == await self.journal.apply(command)
        with pytest.raises(FinanceConflictError):
            await self.journal.apply(
                replace(command, draft=replace(command.draft, amount=Decimal(510))),
            )
        updated = AssetMovementUpdate(
            owner_username=self.owner,
            source=AssetSource.WEB,
            can_write_budget=False,
            now=self.now,
            movement_id=movement.id,
            version=1,
            draft=self.command(Kind.VALUATION, 600, stock.id).draft,
        )
        with pytest.raises(AssetPermissionError):
            await self.journal.update_movement(updated)
        updated = replace(
            updated,
            can_write_budget=True,
            draft=replace(command.draft, amount=Decimal(600)),
        )
        current = await self.journal.update_movement(updated)
        with pytest.raises(FinanceConflictError):
            await self.journal.update_movement(updated)
        stale = await self.journal.apply(command)
        assert (stale.id, stale.version, stale.draft.amount) == (current.id, 1, Decimal(500))
        month = await self.journal.finance.get_month(owner_username=self.owner, now=self.now)
        assert month.transfers[month.currency].contributions == 600
        deleted = await self.journal.set_deleted(self.deletion(current, deleted=True))
        assert (
            await self.journal.finance.get_month(owner_username=self.owner, now=self.now)
        ).closing_balance == 0
        await self.journal.set_deleted(self.deletion(deleted, deleted=False))
        versions = await self.journal.storage.revisions(
            owner_username=self.owner,
            movement_id=current.id,
        )
        assert [(v.version, v.deleted) for v in versions] == [
            (1, False),
            (2, False),
            (3, True),
            (4, False),
        ]

    async def test_preview_matches_dated_foreign_allocation_and_its_replacement(self) -> None:
        day = date(2026, 3, 25)
        rates = self.factory.core.finance_rate_set(day)
        await self.journal.finance.save_rate_set(
            rate_set=replace(rates, rates={**rates.rates, FinanceCurrency.USD: Decimal("80.555")}),
        )
        usd = await self.journal.create_position(
            owner_username=self.owner,
            draft=AssetPositionDraft(
                name="Dollars",
                kind=AssetPositionKind.CASH,
                currency=FinanceCurrency.USD,
                location_id=self.location.id,
                instrument="",
                venue="",
                annual_rate=None,
                matures_on=None,
            ),
        )
        await self.budget.update_opening_balance(
            UpdateOpeningBalanceParams(owner_username=self.owner, now=self.now, amount=Amount(200)),
        )
        april = datetime(2026, 4, 2, tzinfo=UTC)
        await self.budget.ensure_month(replace(self.ensure, now=april))
        command = self.command(Kind.OPENING_BUDGET, 1, usd.id)
        command = replace(command, now=april, draft=replace(command.draft, on_date=day))
        preview = await self.journal.preview_opening(
            AssetOpeningPreviewParams(
                owner_username=self.owner,
                now=april,
                on_date=day,
                position_id=usd.id,
                amount=Decimal(1),
                movement_id=None,
            ),
        )
        assert preview == (Amount("119.44"), FinanceCurrency.RUB)
        movement = await self.journal.apply(command)
        actual = await self.journal.finance.get_month(owner_username=self.owner, now=self.now)
        assert (actual.closing_balance, actual.currency) == preview
        april_month = await self.journal.finance.get_month(owner_username=self.owner, now=april)
        assert april_month.opening_balance == 200
        assert april_month.carry_correction == Decimal("-80.56")
        preview = await self.journal.preview_opening(
            AssetOpeningPreviewParams(
                owner_username=self.owner,
                now=april,
                on_date=day,
                position_id=usd.id,
                amount=Decimal(0),
                movement_id=movement.id,
            ),
        )
        assert preview == (Amount(200), FinanceCurrency.RUB)
        before = await self.journal.finance.get_month(owner_username=self.owner, now=self.now)
        assert before == actual
        await self.journal.update_movement(
            AssetMovementUpdate(
                owner_username=self.owner,
                source=AssetSource.WEB,
                can_write_budget=True,
                now=april,
                movement_id=movement.id,
                version=movement.version,
                draft=replace(movement.draft, kind=Kind.OPENING_EXTERNAL),
            ),
        )
        restored = await self.journal.finance.get_month(owner_username=self.owner, now=self.now)
        assert (restored.closing_balance, restored.currency) == preview

    async def test_backdated_changes_preserve_cash_and_security_balances(self) -> None:
        opening = self.command(Kind.OPENING_EXTERNAL, 100)
        opened = await self.journal.apply(
            replace(opening, draft=replace(opening.draft, on_date=date(2026, 3, 1))),
        )
        stock = await self.position(AssetPositionKind.STOCK)
        trade = self.command(Kind.BUY, 80, stock.id, quantity=4, counter=self.cash.id)
        bought = await self.journal.apply(trade)
        with pytest.raises(FinanceConflictError):
            await self.journal.apply(self.command(Kind.WITHDRAWAL, 21))
        with pytest.raises(FinanceConflictError):
            await self.journal.apply(
                self.command(Kind.SELL, 100, stock.id, quantity=5, counter=self.cash.id),
            )
        with pytest.raises(FinanceConflictError):
            await self.journal.set_deleted(self.deletion(opened, deleted=True))
        with pytest.raises(FinanceConflictError):
            await self.journal.update_movement(
                AssetMovementUpdate(
                    owner_username=self.owner,
                    source=AssetSource.WEB,
                    can_write_budget=True,
                    now=self.now,
                    movement_id=opened.id,
                    version=opened.version,
                    draft=replace(opened.draft, amount=Decimal(79)),
                ),
            )
        disabled = await self.journal.set_deleted(self.deletion(bought, deleted=True))
        await self.journal.apply(self.command(Kind.WITHDRAWAL, 60))
        with pytest.raises(FinanceConflictError):
            await self.journal.set_deleted(self.deletion(disabled, deleted=False))
        revisions = await self.journal.storage.revisions(
            owner_username=self.owner,
            movement_id=bought.id,
        )
        assert [row.deleted for row in revisions] == [False, True]
        month = await self.journal.finance.get_month(owner_username=self.owner, now=self.now)
        assert month.transfers[month.currency].withdrawals == 60

    async def test_linked_income_moves_only_with_group(self) -> None:
        command = self.command(Kind.PAYOUT_TO_BUDGET, 1200)
        movement = await self.journal.apply(
            replace(command, draft=replace(command.draft, note="private portfolio note")),
        )
        assert movement.transaction_id
        month = await self.journal.finance.get_month(owner_username=self.owner, now=self.now)
        assert month.actual_income == month.closing_balance == 1200
        transaction = await self.journal.finance.get_transaction(
            owner_username=self.owner,
            transaction_id=movement.transaction_id,
            now=self.now,
        )
        assert transaction.description == ""
        with pytest.raises(FinanceConflictError):
            await self.budget.set_transaction_deleted(
                SetFinanceTransactionDeletedParams(
                    owner_username=self.owner,
                    now=self.now,
                    period_start=None,
                    transaction_id=transaction.id,
                    version=1,
                    deleted=True,
                ),
            )
        deleted = await self.journal.set_deleted(self.deletion(movement, deleted=True))
        assert (
            await self.journal.finance.get_month(owner_username=self.owner, now=self.now)
        ).actual_income == 0
        restored = await self.journal.set_deleted(self.deletion(deleted, deleted=False))
        assert restored.transaction_id == transaction.id
        assert (
            await self.db_session.scalar(select(func.count()).select_from(FinanceTransactionModel))
            == 1
        )

    async def test_deleted_income_category_preserves_payout_group_lifecycle(self) -> None:
        month = await self.journal.finance.get_month(owner_username=self.owner, now=self.now)
        category = next(c for c in month.categories if c.kind == FinanceKind.INCOME)
        command = self.command(Kind.PAYOUT_TO_BUDGET, 100)
        movement = await self.journal.apply(
            replace(command, draft=replace(command.draft, category_id=category.id)),
        )
        await self.budget.delete_category(
            DeleteFinanceCategoryParams(
                owner_username=self.owner,
                now=self.now,
                category_id=category.id,
            ),
        )
        deleted = await self.journal.set_deleted(self.deletion(movement, deleted=True))
        await self.journal.set_deleted(self.deletion(deleted, deleted=False))
        assert (
            await self.db_session.scalar(
                select(FinanceTransactionModel.former_category_id).where(
                    FinanceTransactionModel.id == movement.transaction_id,
                ),
            )
            == category.stable_id
        )

    async def test_abort_after_linked_accounting_rolls_back_income_and_events(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            AssetDatabaseStorage,
            "insert_movement",
            AsyncMock(
                side_effect=RuntimeError("journal write failed"),
            ),
        )
        with pytest.raises(RuntimeError, match="journal write failed"):
            async with self.db_session.begin_nested():
                await self.journal.apply(self.command(Kind.PAYOUT_TO_BUDGET, 100))
        assert (
            await self.db_session.scalar(select(func.count()).select_from(FinanceTransactionModel))
            == 0
        )
        assert (
            await self.db_session.scalar(select(func.count()).select_from(AssetMovementModel)) == 0
        )
        assert (
            await self.db_session.scalar(select(func.count()).select_from(FinanceEventModel)) == 0
        )

    async def test_read_after_balance_correction_returns_the_version_for_the_next_edit(
        self,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        initial = await self.journal.apply(self.command(Kind.RECONCILE, 12000))
        await self.db_session.commit()
        update = AssetMovementUpdate(
            owner_username=self.owner,
            source=AssetSource.WEB,
            can_write_budget=False,
            now=self.now,
            movement_id=initial.id,
            version=initial.version,
            draft=replace(initial.draft, amount=Decimal(17000)),
        )
        corrected = await self.journal.update_movement(update)
        async with session_maker() as reader:
            await reader.connection()
            analytics = AssetAnalyticsUseCase(
                journal=AssetDatabaseStorage(session=reader),
                storage=FinanceAssetAnalyticsStorage(session=reader),
            )
            query = AssetMovementsParams(owner_username=self.owner, start=None, end=self.now.date())
            task = asyncio.create_task(analytics.movements(query))
            try:
                done, _ = await asyncio.wait({task}, timeout=0.1)
            finally:
                await self.db_session.commit()
            rows = await asyncio.wait_for(task, timeout=5)
        assert not done
        assert [(row.id, row.version, row.draft.amount) for row in rows] == [
            (initial.id, corrected.version, Decimal(17000)),
        ]

    async def test_concurrent_retry_creates_one_budget_posting(
        self,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        await self.db_session.commit()
        command = self.command(Kind.CONTRIBUTION, 1250)

        async def apply() -> AssetMovement:
            async with session_maker.begin() as session:
                return await self.service(session).apply(command)

        first, second = await asyncio.gather(apply(), apply())
        assert first == second
        month = await self.journal.finance.get_month(owner_username=self.owner, now=self.now)
        assert month.closing_balance == -1250
        assert (
            await self.db_session.scalar(select(func.count()).select_from(AssetMovementModel)) == 1
        )
