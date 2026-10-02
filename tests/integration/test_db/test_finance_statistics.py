from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from core.finance.enums import (
    FinanceCurrency,
    FinanceKind,
    FinanceStatisticsCurrency,
    FinanceStatisticsPeriod,
)
from core.finance.exceptions import (
    FinanceConflictError,
    FinanceNotFoundError,
    InvalidFinanceDataError,
)
from core.finance.schemas import (
    Amount,
    ChangeFinanceCurrencyParams,
    CreateFinanceCategoryParams,
    CreateFinanceTransactionParams,
    DeleteFinanceCategoryParams,
    EnsureFinanceMonthParams,
    FinanceActor,
    FinanceCategoryName,
    FinanceHistoricalMonthParams,
    FinanceStatisticsParams,
    ListHistoricalFinanceTransactionsParams,
    SetFinanceTransactionDeletedParams,
    UpdateFinanceCategoryParams,
    UpdateFinanceTransactionParams,
    UpdateOpeningBalanceParams,
)
from core.i18n.enums import LanguageEnum
from infra.postgresql.storages.finance import FinanceDatabaseStorage
from tests.test_cases import StorageTestCase


class TestFinanceStatisticsStorage(StorageTestCase):
    async def test_history_and_statistics_use_owned_snapshots_and_saved_operation_rates(
        self,
    ) -> None:
        await self.factory.db.seed_finance_templates(self.db_session)
        storage = FinanceDatabaseStorage(session=self.db_session)
        use_case = self.factory.core.finance_use_case(storage)
        january = datetime(2026, 1, 15, 12, tzinfo=UTC)
        month = await use_case.ensure_month(
            EnsureFinanceMonthParams(
                owner_username="analytics-owner",
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
                now=january,
            ),
        )
        income = next(row for row in month.categories if row.kind == FinanceKind.INCOME)
        await storage.save_rate_set(rate_set=self.factory.core.finance_rate_set(january.date()))
        first = await use_case.create_transaction(
            CreateFinanceTransactionParams(
                period_start=None,
                owner_username="analytics-owner",
                now=january,
                actor=FinanceActor.web("analytics-owner"),
                draft=self.factory.core.finance_transaction_draft(
                    category_id=income.id,
                    amount=Amount(10),
                    currency=FinanceCurrency.USD,
                    occurred_at=january,
                    description="January",
                ),
            ),
        )
        february = datetime(2026, 2, 2, 12, tzinfo=UTC)
        current = await use_case.ensure_month(
            EnsureFinanceMonthParams(
                owner_username="analytics-owner",
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
                now=february,
            ),
        )
        continued = next(row for row in current.categories if row.stable_id == income.stable_id)
        await use_case.update_category(
            UpdateFinanceCategoryParams(
                owner_username="analytics-owner",
                now=february,
                category_id=continued.id,
                name=FinanceCategoryName("Renamed"),
                planned_amount=None,
                position=continued.position,
            ),
        )
        renamed = (
            await use_case.statistics(
                FinanceStatisticsParams(
                    owner_username="analytics-owner",
                    now=february,
                    period=FinanceStatisticsPeriod.THIS_YEAR,
                    currency=FinanceStatisticsCurrency.USD,
                ),
            )
        ).reports[0]
        assert renamed.income.categories[0].name == "Renamed"
        await storage.save_rate_set(rate_set=self.factory.core.finance_rate_set(february.date()))
        second = await use_case.create_transaction(
            CreateFinanceTransactionParams(
                period_start=None,
                owner_username="analytics-owner",
                now=february,
                actor=FinanceActor.web("analytics-owner"),
                draft=self.factory.core.finance_transaction_draft(
                    category_id=continued.id,
                    amount=Amount(20),
                    currency=FinanceCurrency.USD,
                    occurred_at=february,
                    description="February",
                ),
            ),
        )
        historical = await use_case.historical_month(
            FinanceHistoricalMonthParams(
                owner_username="analytics-owner",
                now=february,
                period_start=date(2026, 1, 1),
            ),
        )
        assert historical.actual_income == 10
        assert historical.categories[0].name != "Renamed"
        rows = await use_case.historical_transactions(
            ListHistoricalFinanceTransactionsParams(
                owner_username="analytics-owner",
                now=february,
                period_start=date(2026, 1, 1),
                include_deleted=False,
            ),
        )
        assert [row.id for row in rows.transactions] == [first.id]
        statistics = (
            await use_case.statistics(
                FinanceStatisticsParams(
                    owner_username="analytics-owner",
                    now=february,
                    period=FinanceStatisticsPeriod.THIS_YEAR,
                    currency=FinanceStatisticsCurrency.USD,
                ),
            )
        ).reports[0]
        assert statistics.income.actual == 30
        assert statistics.income.categories[0].name == "Renamed"
        assert len(statistics.income.categories) == 1
        assert statistics.monthly is None
        await use_case.set_transaction_deleted(
            SetFinanceTransactionDeletedParams(
                period_start=None,
                owner_username="analytics-owner",
                now=february,
                transaction_id=second.id,
                version=second.version,
                deleted=True,
            ),
        )
        filtered = (
            await use_case.statistics(
                FinanceStatisticsParams(
                    owner_username="analytics-owner",
                    now=february,
                    period=FinanceStatisticsPeriod.THIS_MONTH,
                    currency=FinanceStatisticsCurrency.USD,
                ),
            )
        ).reports[0]
        assert filtered.income.actual == 0
        assert filtered.income.previous == 10
        assert filtered.income.change_percent == -100
        with pytest.raises(FinanceNotFoundError):
            await storage.get_month_for_period(
                owner_username="another-owner",
                period_start=date(2026, 1, 1),
            )
        with pytest.raises(FinanceNotFoundError):
            await storage.revisions_for_period(
                owner_username="analytics-owner",
                period_start=date(2026, 1, 1),
                transaction_id=second.id,
            )
        with pytest.raises(InvalidFinanceDataError):
            await use_case.historical_month(
                FinanceHistoricalMonthParams(
                    owner_username="analytics-owner",
                    now=february,
                    period_start=date(2026, 3, 1),
                ),
            )
        await use_case.delete_category(
            DeleteFinanceCategoryParams(
                owner_username="analytics-owner",
                now=february,
                category_id=continued.id,
            ),
        )
        uncategorized = (
            await use_case.statistics(
                FinanceStatisticsParams(
                    owner_username="analytics-owner",
                    now=february,
                    period=FinanceStatisticsPeriod.THIS_YEAR,
                    currency=FinanceStatisticsCurrency.RUB,
                ),
            )
        ).reports[0]
        assert uncategorized.income.categories[0].id == ""
        rate = self.factory.core.finance_rate_set(january.date()).conversion_factor(
            FinanceCurrency.USD,
            FinanceCurrency.RUB,
        )
        assert uncategorized.income.actual == Amount(10 * rate).rounded(FinanceCurrency.RUB)

    async def test_category_rounding_does_not_create_an_uncategorized_amount(self) -> None:
        await self.factory.db.seed_finance_templates(self.db_session)
        storage = FinanceDatabaseStorage(session=self.db_session)
        use_case = self.factory.core.finance_use_case(storage)
        now = datetime(2026, 2, 2, 12, tzinfo=UTC)
        await use_case.ensure_month(
            EnsureFinanceMonthParams(
                owner_username="rounding-owner",
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
                now=now,
            ),
        )
        await storage.save_rate_set(rate_set=self.factory.core.finance_rate_set(now.date()))
        for name in ("First", "Second"):
            month = await use_case.create_category(
                CreateFinanceCategoryParams(
                    owner_username="rounding-owner",
                    now=now,
                    kind=FinanceKind.INCOME,
                    name=FinanceCategoryName(name),
                    planned_amount=None,
                ),
            )
            category = next(row for row in month.categories if row.name == name)
            await use_case.create_transaction(
                CreateFinanceTransactionParams(
                    period_start=None,
                    owner_username="rounding-owner",
                    now=now,
                    actor=FinanceActor.web("rounding-owner"),
                    draft=self.factory.core.finance_transaction_draft(
                        category_id=category.id,
                        amount=Amount(2),
                        currency=FinanceCurrency.AMD,
                        occurred_at=now,
                    ),
                ),
            )
        result = (
            await use_case.statistics(
                FinanceStatisticsParams(
                    owner_username="rounding-owner",
                    now=now,
                    period=FinanceStatisticsPeriod.THIS_MONTH,
                    currency=FinanceStatisticsCurrency.USD,
                ),
            )
        ).reports[0]
        assert result.income.actual == Decimal("0.01")
        assert [row.amount for row in result.income.categories] == [
            Decimal("0.01"),
            Decimal("0.01"),
        ]
        assert result.uncategorized_income == 0
        assert result.uncategorized_expense == 0

    async def test_previous_month_accepts_only_late_operations_and_preserves_current_opening(
        self,
    ) -> None:
        await self.factory.db.seed_finance_templates(self.db_session)
        storage = FinanceDatabaseStorage(session=self.db_session)
        use_case = self.factory.core.finance_use_case(storage)
        january = datetime(2026, 1, 31, 12, tzinfo=UTC)
        february = datetime(2026, 2, 2, 12, tzinfo=UTC)
        month = await use_case.ensure_month(
            EnsureFinanceMonthParams(
                owner_username="late-owner",
                now=january,
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
            ),
        )
        await storage.save_rate_set(rate_set=self.factory.core.finance_rate_set(january.date()))
        category = next(row for row in month.categories if row.kind == FinanceKind.INCOME)
        draft = self.factory.core.finance_transaction_draft(
            category_id=category.id,
            amount=Amount(10),
            currency=FinanceCurrency.USD,
            occurred_at=january,
        )
        original = await use_case.create_transaction(
            CreateFinanceTransactionParams(
                period_start=None,
                owner_username="late-owner",
                now=january,
                actor=FinanceActor.web("late-owner"),
                draft=draft,
            ),
        )
        current = await use_case.ensure_month(
            EnsureFinanceMonthParams(
                owner_username="late-owner",
                now=february,
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
            ),
        )
        late = await use_case.create_transaction(
            CreateFinanceTransactionParams(
                period_start=month.period_start,
                owner_username="late-owner",
                now=february,
                actor=FinanceActor.web("late-owner"),
                draft=draft,
            ),
        )
        assert late.created_at == february
        edited = await use_case.update_transaction(
            UpdateFinanceTransactionParams(
                period_start=month.period_start,
                owner_username="late-owner",
                now=february,
                transaction_id=late.id,
                version=late.version,
                draft=self.factory.core.finance_transaction_draft(
                    category_id=category.id,
                    amount=Amount(25),
                    currency=FinanceCurrency.USD,
                    occurred_at=january,
                ),
            ),
        )
        assert edited.amount == 25
        for deleted in (True, False):
            edited = await use_case.set_transaction_deleted(
                SetFinanceTransactionDeletedParams(
                    period_start=month.period_start,
                    owner_username="late-owner",
                    now=february,
                    transaction_id=late.id,
                    version=edited.version,
                    deleted=deleted,
                ),
            )
        with pytest.raises(FinanceConflictError):
            await use_case.update_transaction(
                UpdateFinanceTransactionParams(
                    period_start=month.period_start,
                    owner_username="late-owner",
                    now=february,
                    transaction_id=original.id,
                    version=original.version,
                    draft=draft,
                ),
            )
        with pytest.raises(FinanceConflictError):
            await use_case.set_transaction_deleted(
                SetFinanceTransactionDeletedParams(
                    period_start=month.period_start,
                    owner_username="late-owner",
                    now=february,
                    transaction_id=original.id,
                    version=original.version,
                    deleted=True,
                ),
            )
        assert (
            await storage.get_month_for_period(
                owner_username="late-owner",
                period_start=month.period_start,
            )
        ).actual_income == 35
        assert (
            (await storage.get_month(owner_username="late-owner", now=february)).opening_balance
            == current.opening_balance
            == 10
        )
        march = datetime(2026, 3, 1, tzinfo=UTC)
        await use_case.ensure_month(
            EnsureFinanceMonthParams(
                owner_username="late-owner",
                now=march,
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
            ),
        )
        with pytest.raises(FinanceConflictError):
            await use_case.update_transaction(
                UpdateFinanceTransactionParams(
                    period_start=month.period_start,
                    owner_username="late-owner",
                    now=march,
                    transaction_id=late.id,
                    version=edited.version,
                    draft=draft,
                ),
            )
        for period in (month.period_start, date(2026, 4, 1)):
            with pytest.raises(FinanceConflictError):
                await use_case.create_transaction(
                    CreateFinanceTransactionParams(
                        period_start=period,
                        owner_username="late-owner",
                        now=march,
                        actor=FinanceActor.web("late-owner"),
                        draft=draft,
                    ),
                )
        with pytest.raises(FinanceNotFoundError):
            await storage.transaction_for_period(
                owner_username="another-owner",
                period_start=month.period_start,
                transaction_id=late.id,
            )

    async def test_all_budget_values_convert_and_native_statistics_keep_currencies_separate(
        self,
    ) -> None:
        await self.factory.db.seed_finance_templates(self.db_session)
        storage = FinanceDatabaseStorage(session=self.db_session)
        use_case = self.factory.core.finance_use_case(storage)
        january = datetime(2026, 1, 15, 12, tzinfo=UTC)
        february = datetime(2026, 2, 2, 12, tzinfo=UTC)
        month = await use_case.ensure_month(
            EnsureFinanceMonthParams(
                owner_username="currency-owner",
                now=january,
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
            ),
        )
        await storage.save_rate_set(rate_set=self.factory.core.finance_rate_set(january.date()))
        await use_case.update_opening_balance(
            UpdateOpeningBalanceParams(
                owner_username="currency-owner",
                now=january,
                amount=Amount(100),
            ),
        )
        category = next(row for row in month.categories if row.kind == FinanceKind.INCOME)
        await use_case.update_category(
            UpdateFinanceCategoryParams(
                owner_username="currency-owner",
                now=january,
                category_id=category.id,
                name=category.name,
                planned_amount=Amount(20),
                position=category.position,
            ),
        )
        await use_case.create_transaction(
            CreateFinanceTransactionParams(
                period_start=None,
                owner_username="currency-owner",
                now=january,
                actor=FinanceActor.web("currency-owner"),
                draft=self.factory.core.finance_transaction_draft(
                    category_id=category.id,
                    amount=Amount(10),
                    currency=FinanceCurrency.USD,
                    occurred_at=january,
                ),
            ),
        )
        current = await use_case.ensure_month(
            EnsureFinanceMonthParams(
                owner_username="currency-owner",
                now=february,
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.EN,
            ),
        )
        await storage.save_rate_set(rate_set=self.factory.core.finance_rate_set(february.date()))
        current = await use_case.change_currency(
            ChangeFinanceCurrencyParams(
                owner_username="currency-owner",
                now=february,
                currency=FinanceCurrency.RUB,
            ),
        )
        continued = next(row for row in current.categories if row.stable_id == category.stable_id)
        await use_case.create_transaction(
            CreateFinanceTransactionParams(
                period_start=None,
                owner_username="currency-owner",
                now=february,
                actor=FinanceActor.web("currency-owner"),
                draft=self.factory.core.finance_transaction_draft(
                    category_id=continued.id,
                    amount=Amount(1),
                    currency=FinanceCurrency.USD,
                    occurred_at=february,
                ),
            ),
        )
        native = await use_case.statistics(
            FinanceStatisticsParams(
                owner_username="currency-owner",
                now=february,
                period=FinanceStatisticsPeriod.THIS_YEAR,
                currency=FinanceStatisticsCurrency.MONTH,
            ),
        )
        assert {row.currency: row.income.actual for row in native.reports} == {
            FinanceCurrency.USD: Amount(10),
            FinanceCurrency.RUB: Amount(80),
        }
        selected = await use_case.statistics(
            FinanceStatisticsParams(
                owner_username="currency-owner",
                now=february,
                period=FinanceStatisticsPeriod.THIS_MONTH,
                currency=FinanceStatisticsCurrency.AMD,
            ),
        )
        report = selected.reports[0]
        assert report.currency == FinanceCurrency.AMD
        assert report.income.actual == 400
        assert report.monthly is not None
        assert report.monthly.currency == FinanceCurrency.AMD
        assert report.monthly.opening_balance == 44000
        assert report.monthly.closing_balance == 44400
        projected = next(
            row for row in report.monthly.categories if row.stable_id == category.stable_id
        )
        assert projected.planned_amount == Amount(8000)
        assert projected.actual_amount == Amount(400)
        assert projected.difference == Amount(-7600)
        assert report.budget_rate_effective_on == february.date()
        unchanged = await storage.get_month(owner_username="currency-owner", now=february)
        assert unchanged.currency == FinanceCurrency.RUB
        assert unchanged.opening_balance == 8800
