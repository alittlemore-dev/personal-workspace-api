from abc import ABC, abstractmethod

from core.finance.schemas import FinanceEvent


class FinanceEventDispatcher(ABC):
    @abstractmethod
    async def publish(self, *, event: FinanceEvent) -> None: ...
