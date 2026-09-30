import asyncio
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.finance.clients import FinanceRateClient
from core.finance.enums import FinanceCurrency, FinanceKind
from core.finance.exceptions import FinanceConflictError, FinanceNotFoundError
from core.finance.schemas import (
    Amount,
    ChangeFinanceCurrencyParams,
    CreateFinanceCategoryParams,
    CreateFinanceTransactionParams,
    DeleteFinanceCategoryParams,
    EnsureFinanceMonthParams,
    FinanceCategoryName,
    FinanceRateSet,
    SetFinanceCategoryArchivedParams,
    SetFinanceTransactionDeletedParams,
    UpdateFinanceCategoryParams,
    UpdateFinanceTransactionParams,
    UpdateOpeningBalanceParams,
)
from core.i18n.enums import LanguageEnum
from infra.postgresql.models.finance import (
    FinanceCategoryModel,
    FinanceMonthCategoryModel,
    FinanceMonthCurrencyChangeModel,
    FinanceMonthModel,
    FinanceTrackerModel,
    FinanceTransactionModel,
)
from infra.postgresql.storages.finance import FinanceDatabaseStorage
from tests.helpers.factory import FactoryHelper
from tests.test_cases import StorageTestCase


class TestFinanceStorage(StorageTestCase):
    async def test_archiving_historical_category_excludes_its_future_rollovers(self) -> None:
        await self.factory.db.seed_finance_templates(self.db_session)
        storage = FinanceDatabaseStorage(session=self.db_session)
        use_case = self.factory.core.finance_use_case(storage)
        january = datetime(2026, 1, 15, 12, tzinfo=UTC)
        first = await use_case.ensure_month(
            EnsureFinanceMonthParams(
                owner_username="owner",
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
                now=january,
            ),
        )
        category = first.categories[0]
        march = await use_case.ensure_month(
            EnsureFinanceMonthParams(
                owner_username="owner",
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
                now=datetime(2026, 3, 15, 12, tzinfo=UTC),
            ),
        )
        await use_case.set_category_archived(
            SetFinanceCategoryArchivedParams(
                owner_username="owner",
                category_id=category.id,
                archived=True,
                now=january,
            ),
        )
        historical = await storage.get_month(
            owner_username="owner",
            now=datetime(2026, 3, 15, 12, tzinfo=UTC),
        )
        assert historical == march
        april = await use_case.ensure_month(
            EnsureFinanceMonthParams(
                owner_username="owner",
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
                now=datetime(2026, 4, 15, 12, tzinfo=UTC),
            ),
        )
        assert all(row.stable_id != category.stable_id for row in april.categories)

    @pytest.mark.parametrize("kind", [FinanceKind.INCOME, FinanceKind.EXPENSE])
    async def test_permanent_category_delete_preserves_transactions_and_revisions(
        self,
        kind: FinanceKind,
    ) -> None:
        await self.factory.db.seed_finance_templates(self.db_session)
        storage = FinanceDatabaseStorage(session=self.db_session)
        use_case = self.factory.core.finance_use_case(storage)
        now = datetime(2026, 9, 15, 12, tzinfo=UTC)
        month = await self.factory.core.finance_use_case(storage).ensure_month(
            EnsureFinanceMonthParams(
                owner_username="owner",
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
                now=now,
            ),
        )
        category = next(category for category in month.categories if category.kind == kind)
        await storage.save_rate_set(
            rate_set=self.factory.core.finance_rate_set(now.date()),
        )
        draft = self.factory.core.finance_transaction_draft(
            category_id=category.id,
            amount=Amount(10),
            currency=FinanceCurrency.USD,
            occurred_at=now,
            description="Original",
        )
        created = await use_case.create_transaction(
            CreateFinanceTransactionParams(owner_username="owner", draft=draft, now=now),
        )
        updated = await use_case.update_transaction(
            UpdateFinanceTransactionParams(
                owner_username="owner",
                transaction_id=created.id,
                draft=replace(draft, description="Corrected"),
                version=created.version,
                now=now,
            ),
        )
        second = await use_case.create_transaction(
            CreateFinanceTransactionParams(
                owner_username="owner",
                draft=replace(draft, amount=Amount(20)),
                now=now,
            ),
        )
        deleted = await use_case.set_transaction_deleted(
            SetFinanceTransactionDeletedParams(
                owner_username="owner",
                transaction_id=second.id,
                version=second.version,
                deleted=True,
                now=now,
            ),
        )
        revisions = await storage.revisions(
            owner_username="owner",
            transaction_id=created.id,
            now=now,
        )
        before = await storage.get_month(owner_username="owner", now=now)
        stored = await self.db_session.get(FinanceTransactionModel, created.id)
        assert stored is not None
        persisted_values = (
            stored.amount_rub,
            stored.rate_set_id,
            stored.created_at,
            stored.updated_at,
            stored.author_username,
        )

        after = await use_case.delete_category(
            DeleteFinanceCategoryParams(owner_username="owner", category_id=category.id, now=now),
        )
        assert all(row.stable_id != category.stable_id for row in after.categories)
        assert await self.db_session.get(FinanceCategoryModel, category.stable_id) is None
        assert (after.actual_income, after.actual_expense, after.closing_balance) == (
            before.actual_income,
            before.actual_expense,
            before.closing_balance,
        )
        assert await storage.get_transaction(
            owner_username="owner",
            transaction_id=created.id,
            now=now,
        ) == replace(updated, category_id=None, category_name="")
        assert await storage.get_transaction(
            owner_username="owner",
            transaction_id=deleted.id,
            now=now,
        ) == replace(deleted, category_id=None, category_name="")
        assert (
            await storage.revisions(
                owner_username="owner",
                transaction_id=created.id,
                now=now,
            )
            == revisions
        )
        assert (
            stored.amount_rub,
            stored.rate_set_id,
            stored.created_at,
            stored.updated_at,
            stored.author_username,
        ) == persisted_values
        assert await storage.list_transactions(
            owner_username="owner",
            include_deleted=False,
            now=now,
        ) == [replace(updated, category_id=None, category_name="")]
        assert (
            len(
                await storage.list_transactions(
                    owner_username="owner",
                    include_deleted=True,
                    now=now,
                ),
            )
            == 2
        )
        restored = await use_case.set_transaction_deleted(
            SetFinanceTransactionDeletedParams(
                owner_username="owner",
                transaction_id=deleted.id,
                version=deleted.version,
                deleted=False,
                now=now,
            ),
        )
        assert restored.category_id is None
        assert restored.kind == kind
        totals = await storage.get_month(owner_username="owner", now=now)
        assert totals.actual_income == (Decimal(30) if kind == FinanceKind.INCOME else Decimal(0))
        assert totals.actual_expense == (Decimal(30) if kind == FinanceKind.EXPENSE else Decimal(0))
        restore_revision = (
            await storage.revisions(
                owner_username="owner",
                transaction_id=deleted.id,
                now=now,
            )
        )[0]
        assert restore_revision.previous_state["categoryId"] is None
        assert restore_revision.previous_state["kind"] == kind.value
        with pytest.raises(FinanceNotFoundError):
            await use_case.update_transaction(
                UpdateFinanceTransactionParams(
                    owner_username="owner",
                    transaction_id=created.id,
                    draft=draft,
                    version=updated.version,
                    now=now,
                ),
            )
        remaining = after.categories[0]
        recategorized = await use_case.update_transaction(
            UpdateFinanceTransactionParams(
                owner_username="owner",
                transaction_id=created.id,
                draft=replace(draft, category_id=remaining.id),
                version=updated.version,
                now=now,
            ),
        )
        assert recategorized.category_id == remaining.id
        assert recategorized.kind == remaining.kind

    async def test_permanent_category_delete_removes_all_month_snapshots_and_lineage(self) -> None:
        await self.factory.db.seed_finance_templates(self.db_session)
        storage = FinanceDatabaseStorage(session=self.db_session)
        use_case = self.factory.core.finance_use_case(storage)
        january = datetime(2026, 1, 15, 12, tzinfo=UTC)
        first = await self.factory.core.finance_use_case(storage).ensure_month(
            EnsureFinanceMonthParams(
                owner_username="owner",
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
                now=january,
            ),
        )
        category = next(
            category for category in first.categories if category.kind == FinanceKind.EXPENSE
        )
        await storage.save_rate_set(
            rate_set=self.factory.core.finance_rate_set(january.date()),
        )
        transaction = await use_case.create_transaction(
            CreateFinanceTransactionParams(
                owner_username="owner",
                draft=self.factory.core.finance_transaction_draft(
                    category_id=category.id,
                    amount=Amount(10),
                    currency=FinanceCurrency.USD,
                    occurred_at=january,
                    description="Historical",
                ),
                now=january,
            ),
        )
        march_date = datetime(2026, 3, 15, 12, tzinfo=UTC)
        march = await self.factory.core.finance_use_case(storage).ensure_month(
            EnsureFinanceMonthParams(
                owner_username="owner",
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
                now=march_date,
            ),
        )
        snapshots = list(
            await self.db_session.scalars(
                select(FinanceMonthCategoryModel).where(
                    FinanceMonthCategoryModel.category_id == category.stable_id,
                ),
            ),
        )
        assert len(snapshots) == 3
        assert sum(row.source_month_category_id is not None for row in snapshots) == 2
        current = next(row for row in march.categories if row.stable_id == category.stable_id)
        await use_case.delete_category(
            DeleteFinanceCategoryParams(
                owner_username="owner",
                category_id=current.id,
                now=march_date,
            ),
        )
        assert (
            await self.db_session.scalar(
                select(func.count())
                .select_from(FinanceMonthCategoryModel)
                .where(
                    FinanceMonthCategoryModel.category_id == category.stable_id,
                ),
            )
            == 0
        )
        historical = await storage.get_month(owner_username="owner", now=january)
        assert historical.actual_expense == Decimal(10)
        assert historical.closing_balance == Decimal(-10)
        assert await storage.get_transaction(
            owner_username="owner",
            transaction_id=transaction.id,
            now=january,
        ) == replace(transaction, category_id=None, category_name="")
        april = await self.factory.core.finance_use_case(storage).ensure_month(
            EnsureFinanceMonthParams(
                owner_username="owner",
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
                now=datetime(2026, 4, 15, 12, tzinfo=UTC),
            ),
        )
        assert all(row.stable_id != category.stable_id for row in april.categories)
        assert april.opening_balance == Decimal(-10)

    async def test_permanent_category_delete_unused_archived_owner_and_missing_id(self) -> None:
        await self.factory.db.seed_finance_templates(self.db_session)
        storage = FinanceDatabaseStorage(session=self.db_session)
        use_case = self.factory.core.finance_use_case(storage)
        now = datetime(2026, 9, 15, 12, tzinfo=UTC)
        owner = await self.factory.core.finance_use_case(storage).ensure_month(
            EnsureFinanceMonthParams(
                owner_username="owner",
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
                now=now,
            ),
        )
        other = await self.factory.core.finance_use_case(storage).ensure_month(
            EnsureFinanceMonthParams(
                owner_username="other",
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
                now=now,
            ),
        )
        category = owner.categories[0]
        for username, category_id in [("other", category.id), ("owner", "missing")]:
            with pytest.raises(FinanceNotFoundError):
                await use_case.delete_category(
                    DeleteFinanceCategoryParams(
                        owner_username=username,
                        category_id=category_id,
                        now=now,
                    ),
                )
        await use_case.set_category_archived(
            SetFinanceCategoryArchivedParams(
                owner_username="owner",
                category_id=category.id,
                archived=True,
                now=now,
            ),
        )
        result = await use_case.delete_category(
            DeleteFinanceCategoryParams(owner_username="owner", category_id=category.id, now=now),
        )
        assert len(result.categories) == len(owner.categories) - 1
        assert result.actual_income == result.actual_expense == result.closing_balance == 0
        assert await storage.get_month(owner_username="other", now=now) == other
        with pytest.raises(FinanceNotFoundError):
            await use_case.delete_category(
                DeleteFinanceCategoryParams(
                    owner_username="owner",
                    category_id=category.id,
                    now=now,
                ),
            )
        recreated = await use_case.create_category(
            CreateFinanceCategoryParams(
                owner_username="owner",
                kind=category.kind,
                name=category.name,
                planned_amount=None,
                now=now,
            ),
        )
        assert next(row for row in recreated.categories if row.name == category.name).stable_id != (
            category.stable_id
        )

    async def test_future_date_requires_its_own_rate_lookup(self) -> None:
        storage = FinanceDatabaseStorage(session=self.db_session)
        friday = date(2026, 9, 25)
        saved_id = await storage.save_rate_set(rate_set=self.factory.core.finance_rate_set(friday))
        cached = await storage.rate_for_date(on_date=friday)
        assert cached is not None
        assert cached[0] == saved_id
        assert await storage.rate_for_date(on_date=date(2026, 9, 26)) is None
        assert await storage.latest_rate_before_date(on_date=date(2026, 9, 26)) == cached
        assert await storage.latest_rate_before_date(on_date=date(2026, 9, 24)) is None
        future_id = await storage.save_rate_set(
            rate_set=self.factory.core.finance_rate_set(date(2026, 9, 28)),
        )
        assert future_id != saved_id
        assert await storage.latest_rate_before_date(on_date=date(2026, 9, 26)) == cached

    async def test_currency_change_converts_plans_and_archived_category_stays_historical(
        self,
    ) -> None:
        await self.factory.db.seed_finance_templates(self.db_session)
        storage = FinanceDatabaseStorage(session=self.db_session)
        use_case = self.factory.core.finance_use_case(storage)
        now = datetime(2026, 9, 15, 12, tzinfo=UTC)
        month = await self.factory.core.finance_use_case(storage).ensure_month(
            EnsureFinanceMonthParams(
                owner_username="owner",
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
                now=now,
            ),
        )
        expense = next(
            category for category in month.categories if category.kind == FinanceKind.EXPENSE
        )
        await use_case.update_opening_balance(
            UpdateOpeningBalanceParams(owner_username="owner", amount=Amount(100), now=now),
        )
        await use_case.update_category(
            UpdateFinanceCategoryParams(
                owner_username="owner",
                category_id=expense.id,
                name=FinanceCategoryName("Food"),
                planned_amount=Amount(50),
                position=0,
                now=now,
            ),
        )
        await storage.save_rate_set(
            rate_set=self.factory.core.finance_rate_set(date(2026, 9, 15)),
        )
        await use_case.create_transaction(
            CreateFinanceTransactionParams(
                owner_username="owner",
                draft=self.factory.core.finance_transaction_draft(
                    category_id=expense.id,
                    amount=Amount(10),
                    currency=FinanceCurrency.USD,
                    occurred_at=now,
                    description="Meal",
                ),
                now=now,
            ),
        )
        converted = await self.factory.core.finance_use_case(storage).change_currency(
            ChangeFinanceCurrencyParams(
                owner_username="owner",
                currency=FinanceCurrency.AMD,
                now=now,
            ),
        )
        assert converted.opening_balance == Decimal(40000)
        assert converted.planned_expense == Decimal(20000)
        assert converted.actual_expense == Decimal(4000)
        assert converted.closing_balance == Decimal(36000)
        currency_change = await self.db_session.scalar(select(FinanceMonthCurrencyChangeModel))
        assert currency_change is not None
        assert Decimal(currency_change.before_state.opening_balance) == 100
        assert Decimal(currency_change.before_state.plans[expense.id]) == 50
        assert Decimal(currency_change.after_state.opening_balance) == 40000
        assert Decimal(currency_change.after_state.plans[expense.id]) == 20000

        archived = await use_case.set_category_archived(
            SetFinanceCategoryArchivedParams(
                owner_username="owner",
                category_id=expense.id,
                archived=True,
                now=now,
            ),
        )
        assert next(
            category for category in archived.categories if category.id == expense.id
        ).archived
        october = await self.factory.core.finance_use_case(storage).ensure_month(
            EnsureFinanceMonthParams(
                owner_username="owner",
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.RU,
                now=datetime(2026, 10, 1, 12, tzinfo=UTC),
            ),
        )
        assert all(category.stable_id != expense.stable_id for category in october.categories)
        assert october.opening_balance == Decimal(36000)

    async def test_initial_month_rolls_forward_without_copying_transactions(self) -> None:
        await self.factory.db.seed_finance_templates(self.db_session)
        storage = FinanceDatabaseStorage(session=self.db_session)
        use_case = self.factory.core.finance_use_case(storage)
        january = datetime(2026, 1, 10, 12, tzinfo=UTC)
        first = await self.factory.core.finance_use_case(storage).ensure_month(
            EnsureFinanceMonthParams(
                owner_username="owner",
                time_zone=ZoneInfo("Asia/Yerevan"),
                language=LanguageEnum.RU,
                now=january,
            ),
        )
        assert first.currency == FinanceCurrency.RUB
        assert first.opening_balance == 0
        assert {category.name for category in first.categories} == {"Еда", "Зарплата"}
        assert all(category.planned_amount is None for category in first.categories)
        assert (
            await self.factory.core.finance_use_case(storage).ensure_month(
                EnsureFinanceMonthParams(
                    owner_username="owner",
                    time_zone=ZoneInfo("UTC"),
                    language=LanguageEnum.EN,
                    now=january,
                ),
            )
        ).id == first.id

        expense = next(
            category for category in first.categories if category.kind == FinanceKind.EXPENSE
        )
        await use_case.update_category(
            UpdateFinanceCategoryParams(
                owner_username="owner",
                category_id=expense.id,
                name=FinanceCategoryName("Еда"),
                planned_amount=Amount(100),
                position=0,
                now=january,
            ),
        )
        await use_case.update_opening_balance(
            UpdateOpeningBalanceParams(owner_username="owner", amount=Amount(50), now=january),
        )
        await storage.save_rate_set(
            rate_set=self.factory.core.finance_rate_set(date(2026, 1, 1)),
        )
        await use_case.create_transaction(
            CreateFinanceTransactionParams(
                owner_username="owner",
                draft=self.factory.core.finance_transaction_draft(
                    category_id=expense.id,
                    amount=Amount(25),
                    currency=FinanceCurrency.RUB,
                    occurred_at=datetime(2026, 1, 15, 10, tzinfo=UTC),
                    description="Lunch",
                ),
                now=january,
            ),
        )
        march = await self.factory.core.finance_use_case(storage).ensure_month(
            EnsureFinanceMonthParams(
                owner_username="owner",
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
                now=datetime(2026, 3, 5, 12, tzinfo=UTC),
            ),
        )
        assert march.period_start == date(2026, 3, 1)
        assert march.opening_balance == Decimal(25)
        assert march.actual_expense == 0
        assert march.planned_expense == Decimal(100)
        assert (
            await self.db_session.scalar(select(func.count()).select_from(FinanceMonthModel)) == 3
        )

        march_expense = next(
            category for category in march.categories if category.kind == FinanceKind.EXPENSE
        )
        await use_case.update_category(
            UpdateFinanceCategoryParams(
                owner_username="owner",
                category_id=march_expense.id,
                name=FinanceCategoryName("Groceries"),
                planned_amount=Amount(120),
                position=0,
                now=datetime(2026, 3, 5, 12, tzinfo=UTC),
            ),
        )
        january_name = await self.db_session.scalar(
            select(FinanceMonthCategoryModel.name).where(
                FinanceMonthCategoryModel.id == expense.id,
            ),
        )
        assert january_name == "Еда"

    async def test_transaction_versions_revisions_and_owner_scope(self) -> None:
        await self.factory.db.seed_finance_templates(self.db_session)
        storage = FinanceDatabaseStorage(session=self.db_session)
        use_case = self.factory.core.finance_use_case(storage)
        now = datetime(2026, 9, 15, 12, tzinfo=UTC)
        month = await self.factory.core.finance_use_case(storage).ensure_month(
            EnsureFinanceMonthParams(
                owner_username="owner",
                time_zone=ZoneInfo("Asia/Yerevan"),
                language=LanguageEnum.EN,
                now=now,
            ),
        )
        await self.factory.core.finance_use_case(storage).ensure_month(
            EnsureFinanceMonthParams(
                owner_username="other",
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.RU,
                now=now,
            ),
        )
        expense = next(
            category for category in month.categories if category.kind == FinanceKind.EXPENSE
        )
        await storage.save_rate_set(
            rate_set=self.factory.core.finance_rate_set(date(2026, 9, 15)),
        )
        draft = self.factory.core.finance_transaction_draft(
            category_id=expense.id,
            amount=Amount(10),
            currency=FinanceCurrency.USD,
            occurred_at=now,
            description="First",
        )
        created = await use_case.create_transaction(
            CreateFinanceTransactionParams(owner_username="owner", draft=draft, now=now),
        )
        assert created.converted_amount == Decimal(10)
        changed = await use_case.update_transaction(
            UpdateFinanceTransactionParams(
                owner_username="owner",
                transaction_id=created.id,
                draft=self.factory.core.finance_transaction_draft(
                    category_id=expense.id,
                    amount=Amount(20),
                    currency=FinanceCurrency.USD,
                    occurred_at=now,
                    description="Corrected",
                ),
                version=created.version,
                now=now,
            ),
        )
        assert changed.version == 2
        with pytest.raises(FinanceConflictError):
            await use_case.update_transaction(
                UpdateFinanceTransactionParams(
                    owner_username="owner",
                    transaction_id=created.id,
                    draft=draft,
                    version=created.version,
                    now=now,
                ),
            )
        with pytest.raises(FinanceNotFoundError):
            await use_case.set_transaction_deleted(
                SetFinanceTransactionDeletedParams(
                    owner_username="other",
                    transaction_id=created.id,
                    version=changed.version,
                    deleted=True,
                    now=now,
                ),
            )
        deleted = await use_case.set_transaction_deleted(
            SetFinanceTransactionDeletedParams(
                owner_username="owner",
                transaction_id=created.id,
                version=changed.version,
                deleted=True,
                now=now,
            ),
        )
        assert deleted.deleted
        assert (await storage.get_month(owner_username="owner", now=now)).actual_expense == 0
        restored = await use_case.set_transaction_deleted(
            SetFinanceTransactionDeletedParams(
                owner_username="owner",
                transaction_id=created.id,
                version=deleted.version,
                deleted=False,
                now=now,
            ),
        )
        assert not restored.deleted
        assert (await storage.get_month(owner_username="owner", now=now)).actual_expense == 20
        assert [
            revision.action.value
            for revision in await storage.revisions(
                owner_username="owner",
                transaction_id=created.id,
                now=now,
            )
        ] == ["restore", "delete", "update"]


async def test_concurrent_ensure_creates_one_month(
    session_maker: async_sessionmaker[AsyncSession],
    setup_migrations: None,
    clear_tables: None,
) -> None:
    _ = (setup_migrations, clear_tables)
    factory = FactoryHelper()
    async with session_maker() as session:
        await factory.db.seed_finance_templates(session)
        await session.commit()

    async def ensure() -> str:
        async with session_maker() as session:
            month = await factory.core.finance_use_case(
                FinanceDatabaseStorage(session=session),
            ).ensure_month(
                EnsureFinanceMonthParams(
                    owner_username="concurrent",
                    time_zone=ZoneInfo("UTC"),
                    language=LanguageEnum.EN,
                    now=datetime(2026, 9, 15, 12, tzinfo=UTC),
                ),
            )
            await session.commit()
            return month.id

    first, second = await asyncio.gather(ensure(), ensure())
    assert first == second
    async with session_maker() as session:
        tracker = await session.scalar(
            select(FinanceTrackerModel).where(
                FinanceTrackerModel.owner_username == "concurrent",
            ),
        )
        assert tracker is not None
        assert (
            await session.scalar(
                select(func.count())
                .select_from(FinanceMonthModel)
                .where(
                    FinanceMonthModel.tracker_id == tracker.id,
                ),
            )
            == 1
        )


async def test_lock_month_refreshes_currency_and_balance_cached_before_another_write(
    session_maker: async_sessionmaker[AsyncSession],
    setup_migrations: None,
    clear_tables: None,
) -> None:
    _ = (setup_migrations, clear_tables)
    factory = FactoryHelper()
    now = datetime(2026, 9, 15, 12, tzinfo=UTC)
    async with session_maker() as session:
        await factory.db.seed_finance_templates(session)
        storage = FinanceDatabaseStorage(session=session)
        await factory.core.finance_use_case(storage).ensure_month(
            EnsureFinanceMonthParams(
                owner_username="owner",
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
                now=now,
            ),
        )
        await storage.save_rate_set(rate_set=factory.core.finance_rate_set())
        await session.commit()

    async with session_maker() as reading_session:
        storage = FinanceDatabaseStorage(session=reading_session)
        initial = await storage.get_month(owner_username="owner", now=now)
        cached = await reading_session.get(FinanceMonthModel, initial.id)
        assert cached is not None
        assert str(cached.currency) == FinanceCurrency.USD.value
        async with session_maker() as writing_session:
            writer = FinanceDatabaseStorage(session=writing_session)
            await factory.core.finance_use_case(writer).change_currency(
                ChangeFinanceCurrencyParams(
                    owner_username="owner",
                    currency=FinanceCurrency.AMD,
                    now=now,
                ),
            )
            await factory.core.finance_use_case(writer).update_opening_balance(
                UpdateOpeningBalanceParams(owner_username="owner", amount=Amount(123), now=now),
            )
            await writing_session.commit()
        refreshed = await storage.lock_month(owner_username="owner", now=now)
        assert refreshed.currency == FinanceCurrency.AMD
        assert refreshed.opening_balance == 123
        assert cached.currency == FinanceCurrency.AMD
        assert cached.opening_balance == 123


async def test_creating_transaction_refreshes_a_category_archived_by_another_session(
    session_maker: async_sessionmaker[AsyncSession],
    setup_migrations: None,
    clear_tables: None,
) -> None:
    _ = (setup_migrations, clear_tables)
    factory = FactoryHelper()
    now = datetime(2026, 9, 15, 12, tzinfo=UTC)
    async with session_maker() as session:
        await factory.db.seed_finance_templates(session)
        storage = FinanceDatabaseStorage(session=session)
        month = await factory.core.finance_use_case(storage).ensure_month(
            EnsureFinanceMonthParams(
                owner_username="owner",
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
                now=now,
            ),
        )
        category = month.categories[0]
        await session.commit()

    async with session_maker() as reading_session:
        cached = await reading_session.get(FinanceMonthCategoryModel, category.id)
        assert cached is not None
        assert bool(cached.accepting_transactions)
        fetching = asyncio.Event()
        release = asyncio.Event()

        async def fetch(*, on_date: date) -> FinanceRateSet:
            fetching.set()
            await release.wait()
            return factory.core.finance_rate_set(on_date)

        rate_client = Mock(spec=FinanceRateClient)
        rate_client.fetch = AsyncMock(side_effect=fetch)
        use_case = factory.core.finance_use_case(
            FinanceDatabaseStorage(session=reading_session),
            rate_client,
        )
        task = asyncio.create_task(
            use_case.create_transaction(
                CreateFinanceTransactionParams(
                    owner_username="owner",
                    now=now,
                    draft=factory.core.finance_transaction_draft(category_id=category.id),
                ),
            ),
        )
        try:
            await asyncio.wait_for(fetching.wait(), timeout=5)
            async with session_maker() as writing_session:
                await factory.core.finance_use_case(
                    FinanceDatabaseStorage(session=writing_session),
                ).set_category_archived(
                    SetFinanceCategoryArchivedParams(
                        owner_username="owner",
                        category_id=category.id,
                        archived=True,
                        now=now,
                    ),
                )
                await writing_session.commit()
            release.set()
            with pytest.raises(FinanceConflictError):
                await asyncio.wait_for(task, timeout=5)
        finally:
            release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        assert not cached.accepting_transactions
        assert (
            await reading_session.scalar(
                select(func.count()).select_from(FinanceTransactionModel),
            )
            == 0
        )


async def test_permanent_category_delete_serializes_with_month_rollover(
    session_maker: async_sessionmaker[AsyncSession],
    setup_migrations: None,
    clear_tables: None,
) -> None:
    _ = (setup_migrations, clear_tables)
    factory = FactoryHelper()
    september = datetime(2026, 9, 15, 12, tzinfo=UTC)
    async with session_maker() as session:
        await factory.db.seed_finance_templates(session)
        month = await factory.core.finance_use_case(
            FinanceDatabaseStorage(session=session),
        ).ensure_month(
            EnsureFinanceMonthParams(
                owner_username="concurrent",
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
                now=september,
            ),
        )
        category = month.categories[0]
        await session.commit()

    started = asyncio.Event()

    async def rollover() -> None:
        async with session_maker() as session:
            started.set()
            october = await factory.core.finance_use_case(
                FinanceDatabaseStorage(session=session),
            ).ensure_month(
                EnsureFinanceMonthParams(
                    owner_username="concurrent",
                    time_zone=ZoneInfo("UTC"),
                    language=LanguageEnum.EN,
                    now=datetime(2026, 10, 15, 12, tzinfo=UTC),
                ),
            )
            assert all(row.stable_id != category.stable_id for row in october.categories)
            await session.commit()

    async with session_maker() as session:
        await factory.core.finance_use_case(
            FinanceDatabaseStorage(session=session),
        ).delete_category(
            DeleteFinanceCategoryParams(
                owner_username="concurrent",
                category_id=category.id,
                now=september,
            ),
        )
        task = asyncio.create_task(rollover())
        try:
            await started.wait()
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=0.1)
            await session.commit()
            await asyncio.wait_for(task, timeout=5)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("mutate", [True, False])
async def test_transaction_loaded_before_category_delete_refreshes_its_category(
    session_maker: async_sessionmaker[AsyncSession],
    setup_migrations: None,
    clear_tables: None,
    mutate: bool,
) -> None:
    _ = (setup_migrations, clear_tables)
    factory = FactoryHelper()
    now = datetime(2026, 9, 15, 12, tzinfo=UTC)
    async with session_maker() as session:
        await factory.db.seed_finance_templates(session)
        storage = FinanceDatabaseStorage(session=session)
        month = await factory.core.finance_use_case(storage).ensure_month(
            EnsureFinanceMonthParams(
                owner_username="owner",
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
                now=now,
            ),
        )
        category = month.categories[0]
        await storage.save_rate_set(
            rate_set=factory.core.finance_rate_set(now.date()),
        )
        transaction = await factory.core.finance_use_case(storage).create_transaction(
            CreateFinanceTransactionParams(
                owner_username="owner",
                draft=factory.core.finance_transaction_draft(
                    category_id=category.id,
                    amount=Amount(10),
                    currency=FinanceCurrency.USD,
                    occurred_at=now,
                    description="Meal",
                ),
                now=now,
            ),
        )
        await session.commit()

    async with session_maker() as read_session:
        cached = await read_session.get(FinanceTransactionModel, transaction.id)
        assert cached is not None
        assert cached.month_category_id == category.id
        async with session_maker() as write_session:
            await factory.core.finance_use_case(
                FinanceDatabaseStorage(session=write_session),
            ).delete_category(
                DeleteFinanceCategoryParams(
                    owner_username="owner",
                    category_id=category.id,
                    now=now,
                ),
            )
            await write_session.commit()
        storage = FinanceDatabaseStorage(session=read_session)
        if not mutate:
            refreshed = await storage.get_transaction(
                owner_username="owner",
                transaction_id=transaction.id,
                now=now,
            )
            assert refreshed == replace(transaction, category_id=None, category_name="")
            return
        deleted = await factory.core.finance_use_case(storage).set_transaction_deleted(
            SetFinanceTransactionDeletedParams(
                owner_username="owner",
                transaction_id=transaction.id,
                version=transaction.version,
                deleted=True,
                now=now,
            ),
        )
        assert deleted.category_id is None
        assert deleted.kind == transaction.kind
        revisions = await storage.revisions(
            owner_username="owner",
            transaction_id=transaction.id,
            now=now,
        )
        assert revisions[0].previous_state["categoryId"] is None
        assert (
            await storage.get_transaction(
                owner_username="owner",
                transaction_id=transaction.id,
                now=now,
            )
        ).category_id is None
        await read_session.commit()
