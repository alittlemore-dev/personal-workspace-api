import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

import httpx
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

from core.finance.clients import FinanceRateClient
from core.finance.enums import FinanceCurrency
from core.finance.exceptions import FinanceRateUnavailableError
from core.finance.schemas import FinanceRateSet
from infra.config.constants import constants


class BankOfRussiaFinanceRateClient(FinanceRateClient):
    def __init__(self, *, http_client: httpx.AsyncClient) -> None:
        self.http_client = http_client

    async def fetch(self, *, on_date: date) -> FinanceRateSet:
        try:
            response = await self.http_client.get(
                constants.finance.bank_of_russia_url,
                params={"date_req": on_date.strftime("%d/%m/%Y")},
            )
            response.raise_for_status()
            return self._parse(response.content, on_date=on_date)
        except (
            httpx.HTTPError,
            ParseError,
            DefusedXmlException,
            ValueError,
            KeyError,
            InvalidOperation,
        ) as error:
            raise FinanceRateUnavailableError from error

    @staticmethod
    def _parse(payload: bytes, *, on_date: date) -> FinanceRateSet:
        root = fromstring(payload)
        day, month, year = (int(part) for part in root.attrib["Date"].split("."))
        effective_on = date(year, month, day)
        if effective_on > on_date:
            raise ValueError
        rates = {FinanceCurrency.RUB: Decimal(1)}
        nominals = {FinanceCurrency.RUB: 1}
        for item in root.findall("Valute"):
            code = item.findtext("CharCode")
            if code not in {"AMD", "USD", "EUR"}:
                continue
            currency = FinanceCurrency(code)
            nominal = int(item.findtext("Nominal") or "0")
            value = Decimal((item.findtext("Value") or "").replace(",", "."))
            if nominal <= 0 or not value.is_finite() or value <= 0:
                raise ValueError
            rates[currency] = value / Decimal(nominal)
            nominals[currency] = nominal
        if set(rates) != set(FinanceCurrency):
            raise ValueError
        return FinanceRateSet(
            effective_on=effective_on,
            fetched_at=datetime.now(UTC),
            rates=rates,
            nominals=nominals,
            payload_hash=hashlib.sha256(payload).hexdigest(),
        )
