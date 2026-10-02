from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import httpx
import pytest

from core.finance.clients import FinanceRateClient
from core.finance.enums import FinanceCurrency
from core.finance.exceptions import FinanceRateUnavailableError, InvalidFinanceDataError
from core.finance.schemas import (
    Amount,
    FinanceCategoryName,
    FinanceTransactionPricing,
    UpdateFinanceTransactionParams,
)
from core.finance.services import (
    FinanceEventService,
    FinanceMonthService,
    FinanceStatisticsService,
    FinanceTelegramAccessService,
)
from core.finance.storages import FinanceStorage
from core.finance.use_cases import FinanceUseCase
from infra.http.finance_rates import BankOfRussiaFinanceRateClient
from tests.test_cases import TestCase


class TestFinance(TestCase):
    def test_money_precision_distinguishes_amd_and_usd(self) -> None:
        FinanceCurrency.AMD.validate_money(Amount(10), positive=True)
        FinanceCurrency.USD.validate_money(Amount("10.25"), positive=True)
        with pytest.raises(InvalidFinanceDataError):
            FinanceCurrency.AMD.validate_money(Amount("10.25"), positive=True)
        with pytest.raises(InvalidFinanceDataError):
            FinanceCurrency.USD.validate_money(Amount(0), positive=True)
        FinanceCurrency.USD.validate_money(Amount(0), positive=False)

    @pytest.mark.parametrize("amount", ["NaN", "Infinity", "-Infinity", "1E+28", "0.001"])
    def test_invalid_money_reports_a_domain_failure(self, amount: str) -> None:
        with pytest.raises(InvalidFinanceDataError):
            FinanceCurrency.USD.validate_money(Amount(amount), positive=True)

    def test_opening_balance_allows_negative_values_and_rounding_uses_currency_precision(
        self,
    ) -> None:
        Amount("-10.25").validate_precision(FinanceCurrency.USD)
        assert Amount("10.5").rounded(FinanceCurrency.AMD) == Amount(11)
        assert Amount("10.255").rounded(FinanceCurrency.USD) == Amount("10.26")

    def test_category_name_normalizes_spacing_and_provides_a_casefolded_key(self) -> None:
        name = FinanceCategoryName("  Food\t shop  ")
        assert name == "Food shop"
        assert name.normalized == "food shop"
        with pytest.raises(InvalidFinanceDataError):
            FinanceCategoryName("  ")
        with pytest.raises(InvalidFinanceDataError):
            FinanceCategoryName("x" * 256)

    def test_category_name_checks_length_after_unicode_casefolding(self) -> None:
        assert FinanceCategoryName("ß" * 127).normalized == "ss" * 127
        with pytest.raises(InvalidFinanceDataError):
            FinanceCategoryName("ß" * 128)

    def test_transaction_pricing_rejects_an_unrepresentable_converted_amount(self) -> None:
        draft = self.factory.core.finance_transaction_draft(amount="100000000000000000")
        with pytest.raises(InvalidFinanceDataError):
            FinanceTransactionPricing.from_draft(
                draft,
                "rate-set",
                self.factory.core.finance_rate_set(),
            )

    def test_currency_conversion_rejects_overflow_before_and_after_rounding(self) -> None:
        month = self.factory.core.finance_month(opening_balance="100000000000000000")
        with pytest.raises(InvalidFinanceDataError):
            month.convert_amounts(FinanceCurrency.RUB, Amount(80))
        with pytest.raises(InvalidFinanceDataError):
            Amount("999999999999999999.995").converted(FinanceCurrency.RUB, Amount(1))

    def test_transaction_month_uses_tracker_time_zone(self) -> None:
        draft = self.factory.core.finance_transaction_draft(
            amount="1",
            occurred_at=datetime(2026, 8, 31, 21, 30, tzinfo=UTC),
        )
        draft.validate(period_start=date(2026, 9, 1), time_zone=ZoneInfo("Asia/Yerevan"))
        with pytest.raises(InvalidFinanceDataError):
            draft.validate(period_start=date(2026, 8, 1), time_zone=ZoneInfo("Asia/Yerevan"))

    @pytest.mark.asyncio
    async def test_bank_of_russia_nominal_is_divided_into_unit_rate(self) -> None:
        response = b"""<?xml version="1.0" encoding="UTF-8"?>
<ValCurs Date="25.09.2026">
<Valute><CharCode>AMD</CharCode><Nominal>100</Nominal><Value>25,0000</Value></Valute>
<Valute><CharCode>USD</CharCode><Nominal>1</Nominal><Value>80,0000</Value></Valute>
<Valute><CharCode>EUR</CharCode><Nominal>1</Nominal><Value>90,0000</Value></Valute>
</ValCurs>"""
        transport = httpx.MockTransport(lambda _request: httpx.Response(200, content=response))
        async with httpx.AsyncClient(transport=transport) as client:
            rates = await BankOfRussiaFinanceRateClient(http_client=client).fetch(
                on_date=date(2026, 9, 26),
            )
        assert rates.effective_on == date(2026, 9, 25)
        assert rates.rates[FinanceCurrency.AMD] == Amount("0.25")
        assert rates.nominals[FinanceCurrency.AMD] == 100
        assert rates.rates[FinanceCurrency.RUB] == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("value", ["", "Infinity", "NaN"])
    async def test_bank_of_russia_rejects_invalid_or_nonfinite_rates(self, value: str) -> None:
        payload = (
            '<ValCurs Date="25.09.2026"><Valute><CharCode>AMD</CharCode>'
            f"<Nominal>1</Nominal><Value>{value}</Value></Valute>"
            "<Valute><CharCode>USD</CharCode><Nominal>1</Nominal><Value>80</Value></Valute>"
            "<Valute><CharCode>EUR</CharCode><Nominal>1</Nominal><Value>90</Value></Valute>"
            "</ValCurs>"
        ).encode()
        transport = httpx.MockTransport(lambda _request: httpx.Response(200, content=payload))
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(FinanceRateUnavailableError):
                await BankOfRussiaFinanceRateClient(http_client=client).fetch(
                    on_date=date(2026, 9, 26),
                )

    @pytest.mark.asyncio
    async def test_description_edit_keeps_original_rate_without_provider_call(self) -> None:
        now = datetime(2026, 9, 15, 12, tzinfo=UTC)
        month = self.factory.core.finance_month(
            categories=[self.factory.core.finance_category()],
        )
        existing = self.factory.core.finance_transaction(occurred_at=now, description="Old")
        storage = Mock(spec=FinanceStorage)
        storage.get_month = AsyncMock(return_value=month)
        storage.lock_month = AsyncMock(return_value=month)
        storage.get_transaction = AsyncMock(return_value=existing)
        storage.update_transaction = AsyncMock(return_value=existing)
        rate_client = Mock(spec=FinanceRateClient)
        rate_client.fetch = AsyncMock()
        use_case = FinanceUseCase(
            statistics_service=FinanceStatisticsService(),
            storage=storage,
            months=FinanceMonthService(storage=storage),
            rate_client=rate_client,
            telegram_access=Mock(spec=FinanceTelegramAccessService),
            events=Mock(spec=FinanceEventService),
        )
        await use_case.update_transaction(
            UpdateFinanceTransactionParams(
                period_start=None,
                owner_username="owner",
                transaction_id=existing.id,
                draft=self.factory.core.finance_transaction_draft(
                    occurred_at=now,
                    description="New",
                ),
                version=1,
                now=now,
            ),
        )
        storage.update_transaction.assert_awaited_once()
        assert storage.update_transaction.await_args.kwargs["write"].pricing is None
        rate_client.fetch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_provider_outage_uses_an_eligible_cached_rate_without_new_writes(self) -> None:
        storage = Mock(spec=FinanceStorage)
        storage.rate_for_date = AsyncMock(return_value=None)
        cached = self.factory.core.finance_rate_set(on_date=date(2026, 9, 25))
        storage.latest_rate_before_date = AsyncMock(return_value=("cached", cached))
        storage.save_rate_set = AsyncMock()
        rate_client = Mock(spec=FinanceRateClient)
        rate_client.fetch = AsyncMock(side_effect=FinanceRateUnavailableError)
        use_case = FinanceUseCase(
            statistics_service=FinanceStatisticsService(),
            storage=storage,
            months=FinanceMonthService(storage=storage),
            rate_client=rate_client,
            telegram_access=Mock(spec=FinanceTelegramAccessService),
            events=Mock(spec=FinanceEventService),
        )
        assert await use_case.resolve_rate_set_id(on_date=date(2026, 9, 26)) == "cached"
        storage.latest_rate_before_date.assert_awaited_once_with(on_date=date(2026, 9, 26))
        storage.save_rate_set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_provider_outage_without_eligible_rates_preserves_the_domain_failure(
        self,
    ) -> None:
        storage = Mock(spec=FinanceStorage)
        storage.rate_for_date = AsyncMock(return_value=None)
        storage.latest_rate_before_date = AsyncMock(return_value=None)
        rate_client = Mock(spec=FinanceRateClient)
        rate_client.fetch = AsyncMock(side_effect=FinanceRateUnavailableError)
        use_case = FinanceUseCase(
            statistics_service=FinanceStatisticsService(),
            storage=storage,
            months=FinanceMonthService(storage=storage),
            rate_client=rate_client,
            telegram_access=Mock(spec=FinanceTelegramAccessService),
            events=Mock(spec=FinanceEventService),
        )
        with pytest.raises(FinanceRateUnavailableError):
            await use_case.resolve_rate_set_id(on_date=date(2026, 9, 26))
