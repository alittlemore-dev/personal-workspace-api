import asyncio
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.finance.assets.enums import AssetMovementKind as Movement
from core.finance.assets.enums import AssetPositionKind, AssetSource
from core.finance.assets.goals import AssetGoal, SetAssetGoalParams
from core.finance.assets.schemas import (
    AssetLocationDraft,
    AssetMovement,
    AssetMovementCommand,
    AssetMovementUpdate,
    AssetPositionDraft,
)
from core.finance.assets.services import AssetMovementService
from core.finance.enums import FinanceCurrency, FinanceEventKind, FinanceKind, FinanceSource
from core.finance.exceptions import FinanceConflictError, FinanceNotFoundError
from core.finance.schemas import (
    Amount,
    CreateFinanceTransactionParams,
    EnsureFinanceMonthParams,
    FinanceActor,
    FinanceRateSet,
    SetFinanceTransactionDeletedParams,
    TelegramFinanceContextParams,
    UpdateFinanceCategoryParams,
    UpdateFinanceTransactionParams,
)
from core.finance.services import FinanceTelegramAccessService
from core.i18n.enums import LanguageEnum
from core.notifications.clients import ReminderSender
from core.notifications.enums import DeliveryStatus
from core.notifications.finance import (
    FinanceDelivery,
    FinanceDeliveryConfig,
    FinanceNotificationFormatter,
    ProcessFinanceNotificationsUseCase,
)
from core.notifications.finance.schemas import AssetFinanceDelivery
from core.telegram.enums import TelegramConnectionState
from core.telegram.exceptions import TelegramAccessError, TelegramServiceError
from core.telegram.schemas import TelegramConnectionSettings, TelegramParticipant
from core.telegram.storages import TelegramAccountSettingsReader
from infra.postgresql.models.finance import FinanceTransactionModel
from infra.postgresql.models.finance_notifications import FinanceDeliveryModel, FinanceEventModel
from infra.postgresql.storages.finance import FinanceDatabaseStorage
from infra.postgresql.storages.finance_assets import AssetDatabaseStorage
from infra.postgresql.storages.finance_notifications import (
    FinanceDatabaseDeliveryStorage,
    FinanceDatabaseEventDispatcher,
)
from infra.postgresql.storages.telegram import TelegramDatabaseStorage
from infra.postgresql.telegram_transaction import TelegramDatabaseTransaction
from tests.helpers.factories.finance_assets import FinanceAssetFactory
from tests.helpers.factory import FactoryHelper
from tests.test_cases import StorageTestCase

NOW = datetime(2026, 9, 15, 12, tzinfo=UTC)


class TestFinanceTelegram(StorageTestCase):
    @pytest_asyncio.fixture(autouse=True)
    async def finance_setup(self) -> None:
        await self.factory.db.seed_finance_templates(self.db_session)
        self.storage = FinanceDatabaseStorage(session=self.db_session)
        self.use_case = self.factory.core.finance_use_case(self.storage)
        self.telegram = TelegramDatabaseStorage(session=self.db_session)
        self.reader = AsyncMock(spec=TelegramAccountSettingsReader)
        self.reader.is_enabled.return_value = True
        self.use_case = replace(
            self.use_case,
            telegram_access=FinanceTelegramAccessService(
                storage=self.telegram,
                settings_reader=self.reader,
            ),
        )
        self.month = await self.use_case.ensure_month(
            EnsureFinanceMonthParams(
                owner_username="owner",
                now=NOW,
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
            ),
        )
        self.category = next(c for c in self.month.categories if c.kind == "expense")
        await self.storage.save_rate_set(rate_set=self.factory.core.finance_rate_set(NOW.date()))
        self.connection = await self.telegram.create_pending_connection(
            owner_username="owner",
            participant=TelegramParticipant(
                user_id=42,
                private_chat_id=42,
                first_name="Boris",
                username="boris",
            ),
            label="Family",
            now=NOW - timedelta(minutes=1),
        )
        self.connection = await self.telegram.set_connection_state(
            connection_id=self.connection.id,
            state=TelegramConnectionState.ACTIVE,
            now=NOW - timedelta(minutes=1),
        )
        self.actor = FinanceActor(
            source=FinanceSource.TELEGRAM,
            identifier="42",
            label=self.connection.label,
            connection_id=self.connection.id,
            telegram_user_id=42,
            private_chat_id=42,
            operation_id="a" * 32,
            month_id=self.month.id,
        )
        self.params = CreateFinanceTransactionParams(
            period_start=None,
            owner_username="owner",
            now=NOW,
            actor=self.actor,
            draft=self.factory.core.finance_transaction_draft(
                category_id=self.category.id,
                occurred_at=NOW,
            ),
        )

    async def test_replayed_confirmation_preserves_actor_and_emits_one_event(self) -> None:
        first = await self.use_case.create_transaction(self.params)
        second = await self.use_case.create_transaction(
            replace(self.params, draft=replace(self.params.draft, amount=Amount(20))),
        )
        assert first.id == second.id
        assert second.amount == 10
        assert second.source == FinanceSource.TELEGRAM
        assert second.author_id == "42"
        assert second.author_label == "Family"
        assert (
            await self.db_session.scalar(select(func.count()).select_from(FinanceTransactionModel))
            == 1
        )
        assert (
            await self.db_session.scalar(select(func.count()).select_from(FinanceEventModel)) == 1
        )
        await self.telegram.set_connection_state(
            connection_id=self.connection.id,
            state=TelegramConnectionState.REVOKED,
            now=NOW,
        )
        persisted = await self.storage.get_transaction(
            owner_username="owner",
            transaction_id=first.id,
            now=NOW,
        )
        assert persisted.author_label == "Family"

    @pytest.mark.parametrize(
        "mode",
        [
            "revoked",
            "pending",
            "blocked",
            "disabled",
            "foreign_owner",
            "foreign_category",
            "changed_month",
        ],
    )
    async def test_confirmation_revalidates_trust_and_scope(self, mode: str) -> None:
        params = self.params
        if mode in ("revoked", "pending", "blocked"):
            await self.telegram.set_connection_state(
                connection_id=self.connection.id,
                state=TelegramConnectionState.REVOKED,
                now=NOW,
            )
        elif mode == "disabled":
            self.reader.is_enabled.return_value = False
        elif mode == "foreign_owner":
            params = replace(params, owner_username="other-owner")
        elif mode == "foreign_category":
            params = replace(params, draft=replace(params.draft, category_id="f" * 32))
        elif mode == "changed_month":
            params = replace(params, actor=replace(params.actor, month_id="other-month"))
        with pytest.raises((TelegramAccessError, FinanceNotFoundError, FinanceConflictError)):
            await self.use_case.create_transaction(params)
        assert (
            await self.db_session.scalar(select(func.count()).select_from(FinanceTransactionModel))
            == 0
        )
        assert (
            await self.db_session.scalar(select(func.count()).select_from(FinanceEventModel)) == 0
        )

    async def test_unavailable_category_is_rejected_before_rate_fetch(self) -> None:
        params = replace(
            self.params,
            draft=replace(
                self.params.draft,
                category_id="f" * 32,
                occurred_at=NOW + timedelta(days=1),
            ),
        )
        with pytest.raises(FinanceNotFoundError):
            await self.use_case.create_transaction(params)
        cast("AsyncMock", self.use_case.rate_client.fetch).assert_not_awaited()
        assert (
            await self.db_session.scalar(select(func.count()).select_from(FinanceEventModel)) == 0
        )

    async def test_revocation_during_rate_fetch_is_rechecked_before_write(self) -> None:
        async def fetch(*, on_date: date) -> FinanceRateSet:
            await self.telegram.set_connection_state(
                connection_id=self.connection.id,
                state=TelegramConnectionState.REVOKED,
                now=NOW,
            )
            return self.factory.core.finance_rate_set(on_date)

        cast("AsyncMock", self.use_case.rate_client.fetch).side_effect = fetch
        params = replace(
            self.params,
            draft=replace(self.params.draft, occurred_at=NOW + timedelta(days=1)),
        )
        with pytest.raises(TelegramAccessError):
            await self.use_case.create_transaction(params)
        assert (
            await self.db_session.scalar(select(func.count()).select_from(FinanceTransactionModel))
            == 0
        )

    async def test_month_boundary_during_rate_fetch_invalidates_confirmation(self) -> None:
        elapsed = [0.0]
        before = NOW.replace(day=30, hour=23, minute=59, second=59)

        async def fetch(*, on_date: date) -> FinanceRateSet:
            elapsed[0] = 2
            return self.factory.core.finance_rate_set(on_date)

        cast("AsyncMock", self.use_case.rate_client.fetch).side_effect = fetch
        params = replace(
            self.params,
            now=before,
            draft=replace(self.params.draft, occurred_at=before),
        )
        with (
            patch("core.finance.use_cases.monotonic", side_effect=lambda: elapsed[0]),
            pytest.raises((FinanceConflictError, FinanceNotFoundError)),
        ):
            await self.use_case.create_transaction(params)
        assert (
            await self.db_session.scalar(select(func.count()).select_from(FinanceTransactionModel))
            == 0
        )
        assert (
            await self.db_session.scalar(select(func.count()).select_from(FinanceEventModel)) == 0
        )

    async def test_delivery_planning_is_unique_and_current_connection_settings_are_loaded(
        self,
    ) -> None:
        await self.use_case.create_transaction(self.params)
        storage = FinanceDatabaseDeliveryStorage(session=self.db_session)
        assert await storage.plan(now=NOW, limit=100) == 1
        assert await storage.plan(now=NOW, limit=100) == 0
        await self.telegram.set_connection_settings(
            connection_id=self.connection.id,
            settings=TelegramConnectionSettings(
                notify_birthday=False,
                notify_memorable_date=False,
                notify_finance_transaction=True,
                notify_finance_limit=True,
                notify_asset_movement=None,
                notify_savings_goal_reached=None,
                notify_assets_month_summary=None,
                notify_deposit_maturity=None,
                language=LanguageEnum.RU,
            ),
        )
        delivery = await storage.claim(
            now=NOW,
            lease_until=NOW + timedelta(minutes=5),
            max_attempts=3,
        )
        assert delivery is not None
        assert delivery.connection is not None
        assert isinstance(delivery, FinanceDelivery)
        assert delivery.connection.notify_finance_transaction
        assert (
            await storage.claim(now=NOW, lease_until=NOW + timedelta(minutes=5), max_attempts=3)
            is None
        )
        await storage.finish(
            delivery=delivery,
            status=DeliveryStatus.DONE,
            now=NOW,
            next_attempt_at=NOW,
        )
        assert (
            await storage.claim(
                now=NOW + timedelta(hours=1),
                lease_until=NOW + timedelta(hours=2),
                max_attempts=3,
            )
            is None
        )
        assert (
            await self.db_session.scalar(select(FinanceDeliveryModel.status)) == DeliveryStatus.DONE
        )

    async def test_operation_and_outbox_rollback_together(self) -> None:
        savepoint = await self.db_session.begin_nested()
        await self.use_case.create_transaction(self.params)
        await savepoint.rollback()
        assert (
            await self.db_session.scalar(select(func.count()).select_from(FinanceTransactionModel))
            == 0
        )
        assert (
            await self.db_session.scalar(select(func.count()).select_from(FinanceEventModel)) == 0
        )

    async def test_commit_failure_rolls_back_financial_operation_and_outbox(self) -> None:
        await self.use_case.create_transaction(self.params)
        with (
            patch.object(self.db_session, "commit", side_effect=SQLAlchemyError()),
            pytest.raises(TelegramServiceError),
        ):
            await TelegramDatabaseTransaction(session=self.db_session).commit()
        assert (
            await self.db_session.scalar(select(func.count()).select_from(FinanceTransactionModel))
            == 0
        )
        assert (
            await self.db_session.scalar(select(func.count()).select_from(FinanceEventModel)) == 0
        )

    async def test_delivery_refresh_observes_revocation_and_expired_lease(self) -> None:
        await self.use_case.create_transaction(self.params)
        storage = FinanceDatabaseDeliveryStorage(session=self.db_session)
        await storage.plan(now=NOW, limit=100)
        delivery = await storage.claim(
            now=NOW,
            lease_until=NOW + timedelta(minutes=5),
            max_attempts=3,
        )
        assert delivery is not None
        await self.telegram.set_connection_state(
            connection_id=self.connection.id,
            state=TelegramConnectionState.REVOKED,
            now=NOW,
        )
        refreshed = await storage.refresh(delivery=delivery, now=NOW)
        assert refreshed is not None
        assert refreshed is not None
        assert refreshed.connection is None
        assert await storage.refresh(delivery=delivery, now=NOW + timedelta(minutes=5)) is None

    async def test_limit_events_rearm_after_deletion_and_restoration(self) -> None:
        await self.use_case.update_category(
            UpdateFinanceCategoryParams(
                owner_username="owner",
                now=NOW,
                category_id=self.category.id,
                name=self.category.name,
                planned_amount=Amount(5),
                position=0,
            ),
        )
        created = await self.use_case.create_transaction(self.params)
        deleted = await self.use_case.set_transaction_deleted(
            SetFinanceTransactionDeletedParams(
                period_start=None,
                owner_username="owner",
                now=NOW,
                transaction_id=created.id,
                version=created.version,
                deleted=True,
            ),
        )
        await self.use_case.set_transaction_deleted(
            SetFinanceTransactionDeletedParams(
                period_start=None,
                owner_username="owner",
                now=NOW,
                transaction_id=created.id,
                version=deleted.version,
                deleted=False,
            ),
        )
        assert (
            await self.db_session.scalar(
                select(func.count())
                .select_from(FinanceEventModel)
                .where(FinanceEventModel.kind == FinanceEventKind.LIMIT),
            )
            == 4
        )
        # Lowering the budget does not produce another event.
        await self.use_case.update_category(
            UpdateFinanceCategoryParams(
                owner_username="owner",
                now=NOW,
                category_id=self.category.id,
                name=self.category.name,
                planned_amount=Amount(1),
                position=0,
            ),
        )
        assert (
            await self.db_session.scalar(
                select(func.count())
                .select_from(FinanceEventModel)
                .where(FinanceEventModel.kind == FinanceEventKind.LIMIT),
            )
            == 4
        )

    async def test_transaction_corrections_rearm_limits_without_creation_event(self) -> None:
        await self.use_case.update_category(
            UpdateFinanceCategoryParams(
                owner_username="owner",
                now=NOW,
                category_id=self.category.id,
                name=self.category.name,
                planned_amount=Amount(5),
                position=0,
            ),
        )
        transaction = await self.use_case.create_transaction(self.params)
        for amount in (20, 1, 10):
            transaction = await self.use_case.update_transaction(
                UpdateFinanceTransactionParams(
                    period_start=None,
                    owner_username="owner",
                    now=NOW,
                    transaction_id=transaction.id,
                    version=transaction.version,
                    draft=replace(self.params.draft, amount=Amount(amount)),
                ),
            )
        assert transaction.author_id == "42"
        assert transaction.author_label == "Family"
        assert (
            await self.db_session.scalar(
                select(func.count())
                .select_from(FinanceEventModel)
                .where(FinanceEventModel.kind == FinanceEventKind.TRANSACTION),
            )
            == 1
        )
        assert (
            await self.db_session.scalar(
                select(func.count())
                .select_from(FinanceEventModel)
                .where(FinanceEventModel.kind == FinanceEventKind.LIMIT),
            )
            == 4
        )

    async def test_late_expiration_retains_terminal_delivery_history_for_90_days(self) -> None:
        await self.use_case.create_transaction(self.params)
        storage = FinanceDatabaseDeliveryStorage(session=self.db_session)
        await storage.plan(now=NOW, limit=100)
        assert await storage.prune(now=NOW + timedelta(days=92), retention=timedelta(days=90)) == 0
        assert (
            await self.db_session.scalar(select(FinanceDeliveryModel.status))
            == DeliveryStatus.EXPIRED
        )
        assert await storage.prune(now=NOW + timedelta(days=183), retention=timedelta(days=90)) == 1
        assert (
            await self.db_session.scalar(select(func.count()).select_from(FinanceDeliveryModel))
            == 0
        )

    async def test_bot_context_synchronizes_account_zone_before_local_rollover(self) -> None:
        reader = cast("AsyncMock", self.use_case.months.time_zone_reader)
        reader.get_time_zone.return_value = ZoneInfo("Asia/Yerevan")
        _, month = await self.use_case.telegram_context(
            TelegramFinanceContextParams(
                telegram_user_id=42,
                private_chat_id=42,
                now=datetime(2026, 10, 31, 22, tzinfo=UTC),
            ),
        )
        assert month is not None
        assert month.time_zone == ZoneInfo("Asia/Yerevan")
        assert month.period_start == date(2026, 11, 1)
        reader.get_time_zone.assert_awaited_once_with(owner_username="owner")

    async def test_lazy_bot_month_creation_requires_existing_tracker(self) -> None:
        _, month = await self.use_case.telegram_context(
            TelegramFinanceContextParams(
                telegram_user_id=42,
                private_chat_id=42,
                now=NOW.replace(month=10),
            ),
        )
        assert month is not None
        assert month.period_start.month == 10
        assert month.categories


async def test_concurrent_confirmations_create_one_transaction_and_outbox_event(
    session_maker: async_sessionmaker[AsyncSession],
    setup_migrations: None,
    clear_tables: None,
) -> None:
    _ = (setup_migrations, clear_tables)
    factory = FactoryHelper()
    async with session_maker() as session:
        await factory.db.seed_finance_templates(session)
        storage = FinanceDatabaseStorage(session=session)
        month = await factory.core.finance_use_case(storage).ensure_month(
            EnsureFinanceMonthParams(
                owner_username="owner",
                now=NOW,
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
            ),
        )
        await storage.save_rate_set(rate_set=factory.core.finance_rate_set(NOW.date()))
        telegram = TelegramDatabaseStorage(session=session)
        connection = await telegram.create_pending_connection(
            owner_username="owner",
            participant=TelegramParticipant(
                user_id=42,
                private_chat_id=42,
                first_name="Boris",
                username="boris",
            ),
            label="Family",
            now=NOW,
        )
        await telegram.set_connection_state(
            connection_id=connection.id,
            state=TelegramConnectionState.ACTIVE,
            now=NOW,
        )
        await session.commit()
    category = next(c for c in month.categories if c.kind == "expense")
    actor = FinanceActor(
        source=FinanceSource.TELEGRAM,
        identifier="42",
        label="Family",
        connection_id=connection.id,
        telegram_user_id=42,
        private_chat_id=42,
        operation_id="b" * 32,
        month_id=month.id,
    )
    params = CreateFinanceTransactionParams(
        period_start=None,
        owner_username="owner",
        now=NOW,
        actor=actor,
        draft=factory.core.finance_transaction_draft(category_id=category.id, occurred_at=NOW),
    )

    async def confirm() -> str:
        async with session_maker() as session:
            storage = FinanceDatabaseStorage(session=session)
            reader = AsyncMock(spec=TelegramAccountSettingsReader)
            reader.is_enabled.return_value = True
            use_case = replace(
                factory.core.finance_use_case(storage),
                telegram_access=FinanceTelegramAccessService(
                    storage=TelegramDatabaseStorage(session=session),
                    settings_reader=reader,
                ),
            )
            result = await use_case.create_transaction(params)
            await session.commit()
            return result.id

    first, second = await asyncio.gather(confirm(), confirm())
    assert first == second
    async with session_maker() as session:
        assert await session.scalar(select(func.count()).select_from(FinanceTransactionModel)) == 1
        assert await session.scalar(select(func.count()).select_from(FinanceEventModel)) == 1

    async with session_maker() as session:
        deliveries = FinanceDatabaseDeliveryStorage(session=session)
        await deliveries.plan(now=NOW, limit=100)
        await session.commit()

    async def claim() -> FinanceDelivery | AssetFinanceDelivery | None:
        async with session_maker() as session:
            result = await FinanceDatabaseDeliveryStorage(session=session).claim(
                now=NOW,
                lease_until=NOW + timedelta(minutes=5),
                max_attempts=3,
            )
            await session.commit()
            return result

    claimed = await asyncio.gather(claim(), claim())
    owned = [delivery for delivery in claimed if delivery is not None]
    assert len(owned) == 1
    async with session_maker() as session:
        deliveries = FinanceDatabaseDeliveryStorage(session=session)
        recovered = await deliveries.claim(
            now=NOW + timedelta(minutes=5),
            lease_until=NOW + timedelta(minutes=10),
            max_attempts=3,
        )
        assert recovered is not None
        assert recovered.attempts == 2
        await deliveries.finish(
            delivery=owned[0],
            status=DeliveryStatus.DONE,
            now=NOW + timedelta(minutes=5),
            next_attempt_at=NOW,
        )
        assert (
            await session.scalar(select(FinanceDeliveryModel.status)) == DeliveryStatus.IN_PROGRESS
        )
        await session.commit()


class TestAssetNotifications(StorageTestCase):
    @pytest_asyncio.fixture(autouse=True)
    async def prepare(self) -> None:
        await self.factory.db.seed_finance_templates(self.db_session)
        self.finance = self.factory.core.finance_use_case(
            FinanceDatabaseStorage(session=self.db_session),
        )
        self.telegram = TelegramDatabaseStorage(session=self.db_session)
        self.deliveries = FinanceDatabaseDeliveryStorage(session=self.db_session)
        dispatcher = self.finance.events.dispatcher
        assert isinstance(dispatcher, FinanceDatabaseEventDispatcher)
        self.notices = dispatcher.assets
        self.journal = AssetMovementService(
            storage=AssetDatabaseStorage(session=self.db_session),
            finance=self.finance.storage,
            months=self.finance.months,
            events=self.finance.events,
            rate_client=self.finance.rate_client,
        )
        self.sender = AsyncMock(spec=ReminderSender)
        self.accounts = AsyncMock(spec=TelegramAccountSettingsReader)
        self.accounts.can_notify.return_value = True
        self.worker = ProcessFinanceNotificationsUseCase(
            storage=self.deliveries,
            assets=self.notices,
            finance_storage=self.finance.storage,
            settings_reader=self.accounts,
            sender=self.sender,
            formatter=FinanceNotificationFormatter(),
            transaction=TelegramDatabaseTransaction(session=self.db_session),
            config=FinanceDeliveryConfig(
                batch_size=100,
                max_attempts=3,
                retry_interval=timedelta(minutes=1),
                claim_lease=timedelta(minutes=5),
                retention=timedelta(days=90),
            ),
        )
        self.flags = TelegramConnectionSettings(
            notify_birthday=False,
            notify_memorable_date=False,
            notify_finance_transaction=False,
            notify_finance_limit=False,
            notify_asset_movement=False,
            notify_savings_goal_reached=False,
            notify_assets_month_summary=False,
            notify_deposit_maturity=False,
            language=LanguageEnum.EN,
        )
        self.start = datetime(2026, 12, 1, 12, tzinfo=UTC)
        self.ensure = EnsureFinanceMonthParams(
            owner_username="owner",
            now=self.start,
            language=LanguageEnum.EN,
            time_zone=ZoneInfo("UTC"),
        )
        self.month = await self.finance.ensure_month(self.ensure)
        await self.finance.storage.save_rate_set(
            rate_set=self.factory.core.finance_rate_set(self.start.date()),
        )
        location = await self.journal.create_location(
            owner_username="owner",
            draft=AssetLocationDraft(name="Savings"),
        )
        self.account = AssetPositionDraft(
            name="Term deposit",
            location_id=location.id,
            kind=AssetPositionKind.DEPOSIT,
            currency=FinanceCurrency.USD,
            instrument="",
            venue="",
            annual_rate=None,
            matures_on=date(2027, 1, 8),
        )
        self.deposit = await self.journal.create_position(
            owner_username="owner",
            draft=self.account,
        )
        await self.move(Movement.OPENING_EXTERNAL, 1)

    async def subscribe(self, owner: str, chat: int, settings: TelegramConnectionSettings) -> str:
        connection = await self.telegram.create_pending_connection(
            owner_username=owner,
            participant=TelegramParticipant(
                user_id=chat,
                private_chat_id=chat,
                first_name=owner,
                username="",
            ),
            label=owner,
            now=self.start - timedelta(hours=1),
        )
        await self.telegram.set_connection_state(
            connection_id=connection.id,
            state=TelegramConnectionState.ACTIVE,
            now=self.start - timedelta(hours=1),
        )
        await self.telegram.set_connection_settings(connection_id=connection.id, settings=settings)
        return connection.id

    async def move(self, kind: Movement, amount: int) -> AssetMovement:
        draft = FinanceAssetFactory.movement(
            kind,
            self.start.date(),
            self.deposit.id,
            amount=amount,
        ).draft
        return await self.journal.apply(
            AssetMovementCommand(
                owner_username="owner",
                source=AssetSource.WEB,
                request_id=uuid4(),
                now=self.start,
                can_write_budget=True,
                draft=draft,
            ),
        )

    async def test_payout_delivery_selects_one_language_and_message_per_recipient(self) -> None:
        both = replace(
            self.flags,
            notify_asset_movement=True,
            notify_finance_transaction=True,
            language=LanguageEnum.RU,
        )
        first = await self.subscribe("owner", 42, both)
        await self.subscribe("owner", 43, replace(self.flags, notify_finance_transaction=True))
        await self.subscribe("unrelated", 44, both)
        await self.move(Movement.PAYOUT_TO_BUDGET, 250)
        assert await self.worker.run(now=self.start) == 2
        messages = {
            call.kwargs["private_chat_id"]: call.kwargs["text"]
            for call in self.sender.send.await_args_list
        }
        assert set(messages) == {42, 43}
        assert "Выплата в бюджет" in messages[42]
        assert "250.00 USD" in messages[42]
        assert "tab=transactions&year=2026&month=12&assetPosition=" in messages[42]
        assert "Income: 250.00 USD" in messages[43]
        assert await self.worker.run(now=self.start) == 0
        updated = await self.telegram.set_connection_settings(
            connection_id=first,
            settings=replace(
                both,
                notify_asset_movement=None,
                notify_savings_goal_reached=None,
                notify_assets_month_summary=None,
                notify_deposit_maturity=None,
            ),
        )
        assert updated.notify_asset_movement
        await self.move(Movement.CONTRIBUTION, 10)
        await self.deliveries.plan(now=self.start, limit=100)
        await self.telegram.set_connection_settings(connection_id=first, settings=self.flags)
        assert await self.worker.run(now=self.start) == 0

    async def test_contributions_reach_only_each_owners_subscribed_chat(self) -> None:
        await self.subscribe(
            "owner",
            42,
            replace(self.flags, notify_asset_movement=True, language=LanguageEnum.RU),
        )
        other = "second-owner"
        await self.subscribe(other, 43, replace(self.flags, notify_asset_movement=True))
        await self.finance.ensure_month(replace(self.ensure, owner_username=other))
        location = await self.journal.create_location(
            owner_username=other,
            draft=AssetLocationDraft(name="Second portfolio"),
        )
        position = await self.journal.create_position(
            owner_username=other,
            draft=replace(self.account, location_id=location.id, name="Reserve"),
        )
        await self.move(Movement.CONTRIBUTION, 81)
        await self.journal.apply(
            AssetMovementCommand(
                owner_username=other,
                source=AssetSource.PAT,
                request_id=uuid4(),
                now=self.start,
                can_write_budget=True,
                draft=FinanceAssetFactory.movement(
                    Movement.CONTRIBUTION,
                    self.start.date(),
                    position.id,
                    amount=57,
                ).draft,
            ),
        )
        assert await self.worker.run(now=self.start) == 2
        messages = {
            call.kwargs["private_chat_id"]: call.kwargs["text"]
            for call in self.sender.send.await_args_list
        }
        assert "Взнос" in messages[42]
        assert "81.00 USD" in messages[42]
        assert "Contribution" in messages[43]
        assert "57.00 USD" in messages[43]

    @pytest.mark.parametrize("mode", ["revoked", "corrected", "notifications_disabled"])
    async def test_asset_movement_refresh_before_sending(self, mode: str) -> None:
        recipient = await self.subscribe(
            "owner",
            42,
            replace(self.flags, notify_asset_movement=True),
        )
        movement = await self.move(Movement.CONTRIBUTION, 75)
        await self.deliveries.plan(now=self.start, limit=100)
        if mode == "revoked":
            await self.telegram.set_connection_state(
                connection_id=recipient,
                state=TelegramConnectionState.REVOKED,
                now=self.start,
            )
        elif mode == "notifications_disabled":
            self.accounts.can_notify.return_value = False
        else:
            await self.journal.update_movement(
                AssetMovementUpdate(
                    owner_username="owner",
                    source=AssetSource.PAT,
                    can_write_budget=True,
                    now=self.start,
                    movement_id=movement.id,
                    version=1,
                    draft=replace(movement.draft, amount=Decimal(50)),
                ),
            )
        assert await self.worker.run(now=self.start) == 0
        self.sender.send.assert_not_awaited()

    async def test_goal_rearms_before_delivery_and_sends_once_after_recrossing(self) -> None:
        await self.subscribe("owner", 42, replace(self.flags, notify_savings_goal_reached=True))
        await self.notices.analytics.set_goal(
            SetAssetGoalParams(
                owner_username="owner",
                goal=AssetGoal(
                    month=self.start.date(),
                    percent=Decimal(10),
                    all_income=True,
                    category_ids=(),
                ),
            ),
        )
        salary = next(c for c in self.month.categories if c.kind == FinanceKind.INCOME)
        await self.finance.create_transaction(
            CreateFinanceTransactionParams(
                owner_username="owner",
                now=self.start,
                period_start=None,
                actor=FinanceActor.web("owner"),
                draft=self.factory.core.finance_transaction_draft(
                    category_id=salary.id,
                    amount="1000",
                    currency=FinanceCurrency.USD,
                    occurred_at=self.start,
                ),
            ),
        )
        await self.move(Movement.CONTRIBUTION, 100)
        await self.deliveries.plan(now=self.start, limit=100)
        await self.move(Movement.WITHDRAWAL, 20)
        assert await self.worker.run(now=self.start) == 0
        await self.move(Movement.CONTRIBUTION, 20)
        assert await self.worker.run(now=self.start) == 1
        assert "Savings goal reached" in self.sender.send.await_args.kwargs["text"]
        await self.move(Movement.WITHDRAWAL, 20)
        await self.move(Movement.CONTRIBUTION, 20)
        assert await self.worker.run(now=self.start) == 0
        assert (
            await self.db_session.scalar(
                select(func.count())
                .select_from(FinanceEventModel)
                .where(FinanceEventModel.kind == FinanceEventKind.SAVINGS_GOAL),
            )
            == 1
        )

    async def test_maturity_reminder_links_to_the_current_month_across_new_year(self) -> None:
        await self.subscribe("owner", 43, replace(self.flags, notify_deposit_maturity=True))
        await self.journal.update_position(
            owner_username="owner",
            position_id=self.deposit.id,
            draft=replace(self.account, matures_on=date(2027, 1, 3)),
        )
        now = datetime(2026, 12, 27, 9, tzinfo=UTC)
        await self.notices.plan_calendar(now)
        assert await self.worker.run(now=now) == 1
        text = self.sender.send.await_args.kwargs["text"]
        assert "01/03/2027" in text
        assert "tab=overview&year=2026&month=12" in text

    async def test_calendar_replans_in_new_zone_and_expired_deposit_date_is_cancelled(
        self,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        await self.subscribe(
            "owner",
            42,
            replace(self.flags, notify_assets_month_summary=True, notify_deposit_maturity=True),
        )
        midnight = datetime(2027, 1, 1, tzinfo=UTC)
        await self.notices.plan_calendar(midnight + timedelta(hours=8, minutes=59))
        assert (
            await self.db_session.scalar(select(func.count()).select_from(FinanceEventModel)) == 0
        )
        early = midnight + timedelta(hours=9)
        await self.db_session.commit()

        async def plan() -> None:
            async with session_maker.begin() as session:
                dispatcher = self.factory.core.finance_use_case(
                    FinanceDatabaseStorage(session=session),
                ).events.dispatcher
                assert isinstance(dispatcher, FinanceDatabaseEventDispatcher)
                await dispatcher.assets.plan_calendar(early)

        await asyncio.gather(plan(), plan())
        assert (
            await self.db_session.scalar(select(func.count()).select_from(FinanceEventModel)) == 2
        )
        zones = cast("AsyncMock", self.notices.time_zones)
        zones.get_time_zone.return_value = ZoneInfo("America/New_York")
        assert await self.worker.run(now=early) == 0
        await self.journal.update_position(
            owner_username="owner",
            position_id=self.deposit.id,
            draft=replace(self.account, matures_on=date(2027, 1, 15)),
        )
        later = midnight + timedelta(hours=14)
        await self.notices.plan_calendar(later)
        assert await self.worker.run(now=later) == 1
        monthly = self.sender.send.await_args.kwargs["text"]
        assert "Monthly assets" in monthly
        assert "12/2026" in monthly
        assert "Capital" in monthly
        followup = later + timedelta(days=7)
        await self.notices.plan_calendar(followup)
        assert await self.worker.run(now=followup) == 1
        assert "Deposit maturity" in self.sender.send.await_args.kwargs["text"]
        assert "01/15/2027" in self.sender.send.await_args.kwargs["text"]
        assert await self.worker.run(now=followup) == 0
