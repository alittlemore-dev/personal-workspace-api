from datetime import date
from typing import cast
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from httpx import codes

from core.finance.enums import (
    FinanceCurrency,
    FinanceKind,
    FinanceStatisticsCurrency,
    FinanceStatisticsPeriod,
)
from core.finance.schemas import (
    Amount,
    CreateFinanceCategoryParams,
    CreateFinanceTransactionParams,
    EnsureFinanceMonthParams,
    FinanceActor,
    FinanceCategoryName,
    FinanceStatisticsComposition,
    FinanceStatisticsParams,
    FinanceStatisticsSource,
    FinanceStatisticsWindow,
)
from core.finance.services import FinanceStatisticsService
from core.finance.use_cases import FinanceUseCase
from core.i18n.enums import LanguageEnum
from tests.test_cases import ApiTestCase
from tests.unit.conftest import TEST_CURRENT_DATETIME, TEST_USERNAME


class TestFinanceApi(ApiTestCase):
    @pytest_asyncio.fixture(autouse=True)
    async def setup(self) -> None:
        self.use_case = cast("Mock", await self.container.container.get(FinanceUseCase))

    def test_ensure_month_uses_account_zone_and_canonical_language(self) -> None:
        self.use_case.ensure_month.return_value = self.factory.core.finance_month()
        response = self.api.client.post(
            "/api/finance/current-month/ensure",
            json={"language": "ru"},
        )
        self.asserts.status(response=response, expected_status=codes.OK)
        self.use_case.ensure_month.assert_awaited_once_with(
            EnsureFinanceMonthParams(
                owner_username=TEST_USERNAME,
                now=TEST_CURRENT_DATETIME,
                time_zone=ZoneInfo("UTC"),
                language=LanguageEnum.RU,
            ),
        )
        assert isinstance(self.use_case.ensure_month.await_args.args[0].language, LanguageEnum)
        assert response.json()["timezoneName"] == "UTC"

    def test_create_category_passes_validated_value_objects(self) -> None:
        self.use_case.create_category.return_value = self.factory.core.finance_month()
        response = self.api.client.post(
            "/api/finance/current-month/categories",
            json={"kind": "expense", "name": "  Food   shop  ", "plannedAmount": "10.25"},
        )
        self.asserts.status(response=response, expected_status=codes.CREATED)
        self.use_case.create_category.assert_awaited_once_with(
            CreateFinanceCategoryParams(
                owner_username=TEST_USERNAME,
                now=TEST_CURRENT_DATETIME,
                kind=FinanceKind.EXPENSE,
                name=FinanceCategoryName("Food shop"),
                planned_amount=Amount("10.25"),
            ),
        )
        params = self.use_case.create_category.await_args.args[0]
        assert isinstance(params.name, FinanceCategoryName)
        assert isinstance(params.planned_amount, Amount)

    def test_create_transaction_decodes_money_and_timestamp(self) -> None:
        self.use_case.create_transaction.return_value = self.factory.core.finance_transaction()
        response = self.api.client.post(
            "/api/finance/current-month/transactions",
            json={
                "categoryId": "category",
                "amount": "10.25",
                "currency": "USD",
                "occurredAt": TEST_CURRENT_DATETIME.isoformat(),
                "description": "Meal",
            },
        )
        self.asserts.status(response=response, expected_status=codes.CREATED)
        self.use_case.create_transaction.assert_awaited_once_with(
            CreateFinanceTransactionParams(
                period_start=None,
                owner_username=TEST_USERNAME,
                now=TEST_CURRENT_DATETIME,
                draft=self.factory.core.finance_transaction_draft(
                    amount="10.25",
                    currency=FinanceCurrency.USD,
                    occurred_at=TEST_CURRENT_DATETIME,
                    description="Meal",
                ),
                actor=FinanceActor.web(TEST_USERNAME),
            ),
        )
        assert response.json()["source"] == "web"
        assert response.json()["authorId"] == "owner"
        assert response.json()["authorLabel"] == "owner"
        assert isinstance(self.use_case.create_transaction.await_args.args[0].draft.amount, Amount)

    def test_list_responses_map_domain_aggregates(self) -> None:
        transaction = self.factory.core.finance_transaction()
        revision = self.factory.core.finance_transaction_revision()
        self.use_case.list_transactions.return_value = self.factory.core.finance_transactions(
            transactions=[transaction],
        )
        self.use_case.revisions.return_value = self.factory.core.finance_revisions(
            revisions=[revision],
        )
        response = self.api.client.get(
            "/api/finance/current-month/transactions",
            params={"include_deleted": "false"},
        )
        self.asserts.status(response=response, expected_status=codes.OK)
        assert response.json()["transactions"][0]["id"] == transaction.id
        response = self.api.client.get(
            f"/api/finance/current-month/transactions/{transaction.id}/revisions",
        )
        self.asserts.status(response=response, expected_status=codes.OK)
        assert response.json()["revisions"][0]["previousState"] == revision.previous_state

    def test_historical_month_validates_date_and_keeps_read_only_contract(self) -> None:
        self.use_case.historical_month.return_value = self.factory.core.finance_month()
        response = self.api.client.get("/api/finance/months/2026/9")
        self.asserts.status(response=response, expected_status=codes.OK)
        assert response.json()["periodStart"] == "2026-09-01"
        assert self.use_case.historical_month.await_args.args[0].period_start == date(2026, 9, 1)
        assert self.use_case.historical_month.await_args.args[0].owner_username == TEST_USERNAME
        invalid = self.api.client.get("/api/finance/months/2026/13")
        self.asserts.status(response=invalid, expected_status=codes.BAD_REQUEST)
        write = self.api.client.put(
            "/api/finance/months/2026/9/opening-balance",
            json={"amount": 50},
        )
        assert write.status_code in (codes.NOT_FOUND, codes.METHOD_NOT_ALLOWED)

    @pytest.mark.parametrize(
        "currency",
        [FinanceStatisticsCurrency.USD, FinanceStatisticsCurrency.MONTH],
    )
    def test_statistics_maps_nested_decimal_and_period_response(
        self,
        currency: FinanceStatisticsCurrency,
    ) -> None:
        month = self.factory.core.finance_month()
        now = TEST_CURRENT_DATETIME
        params = FinanceStatisticsParams(
            owner_username=TEST_USERNAME,
            now=now,
            period=FinanceStatisticsPeriod.THIS_MONTH,
            currency=currency,
        )
        window, previous = FinanceStatisticsWindow.for_period(params.period, now, month.time_zone)
        self.use_case.statistics.return_value = FinanceStatisticsService().compose_result(
            FinanceStatisticsComposition(
                params=params,
                month=month,
                window=window,
                previous_window=previous,
                source=FinanceStatisticsSource(
                    available_since=date(2026, 9, 1),
                    facts=[],
                    currencies=[FinanceCurrency.USD],
                ),
                budget_rate=None,
            ),
        )
        response = self.api.client.get(
            "/api/finance/statistics",
            params={"period": "thisMonth", "currency": currency},
        )
        self.asserts.status(response=response, expected_status=codes.OK)
        assert response.json()["currency"] == currency
        payload = response.json()["reports"][0]
        assert payload["income"]["actual"] == "0.00"
        assert payload["income"]["changePercent"] is None
        assert payload["window"]["granularity"] == "day"
        assert payload["monthly"]["currency"] == month.currency
        assert payload["uncategorizedIncome"] == "0.00"
        self.use_case.statistics.assert_awaited_once_with(params)
        invalid = self.api.client.get(
            "/api/finance/statistics",
            params={"period": "arbitrary", "currency": "USD"},
        )
        self.asserts.status(response=invalid, expected_status=codes.BAD_REQUEST)

    def test_historical_transaction_writes_preserve_owner_period_and_version(self) -> None:
        transaction = self.factory.core.finance_transaction()
        self.use_case.create_transaction.return_value = transaction
        self.use_case.update_transaction.return_value = transaction
        self.use_case.set_transaction_deleted.return_value = transaction
        draft = {
            "categoryId": "category",
            "amount": "10",
            "currency": "USD",
            "occurredAt": TEST_CURRENT_DATETIME.isoformat(),
            "description": "Late",
        }
        created = self.api.client.post("/api/finance/months/2026/8/transactions", json=draft)
        self.asserts.status(response=created, expected_status=codes.CREATED)
        params = self.use_case.create_transaction.await_args.args[0]
        assert params.period_start == date(2026, 8, 1)
        assert params.owner_username == TEST_USERNAME
        assert params.now == TEST_CURRENT_DATETIME
        assert "createdAt" in created.json()
        updated = self.api.client.put(
            "/api/finance/months/2026/8/transactions/transaction",
            json={**draft, "version": 4},
        )
        self.asserts.status(response=updated, expected_status=codes.OK)
        assert self.use_case.update_transaction.await_args.args[0].version == 4
        deleted = self.api.client.delete(
            "/api/finance/months/2026/8/transactions/transaction",
            params={"version": 5},
        )
        self.asserts.status(response=deleted, expected_status=codes.OK)
        deletion = self.use_case.set_transaction_deleted.await_args.args[0]
        assert deletion.period_start == date(2026, 8, 1)
        assert deletion.deleted
        assert deletion.version == 5
        restored = self.api.client.post(
            "/api/finance/months/2026/8/transactions/transaction/restore",
            json={"version": 6},
        )
        self.asserts.status(response=restored, expected_status=codes.OK)
        restoration = self.use_case.set_transaction_deleted.await_args.args[0]
        assert restoration.period_start == date(2026, 8, 1)
        assert not restoration.deleted
        assert restoration.version == 6
