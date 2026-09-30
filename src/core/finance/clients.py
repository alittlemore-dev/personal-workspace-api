from abc import ABC, abstractmethod
from datetime import date

from core.finance.schemas import FinanceRateSet


class FinanceRateClient(ABC):
    @abstractmethod
    async def fetch(self, *, on_date: date) -> FinanceRateSet: ...
