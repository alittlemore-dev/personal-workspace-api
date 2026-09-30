from typing import cast
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest_asyncio
from httpx import codes

from core.finance.enums import FinanceCurrency, FinanceKind
from core.finance.schemas import (
    Amount,
    CreateFinanceCategoryParams,
    CreateFinanceTransactionParams,
    EnsureFinanceMonthParams,
    FinanceCategoryName,
)
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
                owner_username=TEST_USERNAME,
                now=TEST_CURRENT_DATETIME,
                draft=self.factory.core.finance_transaction_draft(
                    amount="10.25",
                    currency=FinanceCurrency.USD,
                    occurred_at=TEST_CURRENT_DATETIME,
                    description="Meal",
                ),
            ),
        )
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
