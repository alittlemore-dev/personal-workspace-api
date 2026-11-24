from abc import ABC, abstractmethod
from datetime import datetime

from core.finance.schemas import FinanceEvent


class FinanceEventDispatcher(ABC):
    @abstractmethod
    async def publish(self, *, event: FinanceEvent) -> None: ...

    @abstractmethod
    async def publish_asset_movement(
        self,
        *,
        owner_username: str,
        movement_id: str,
        version: int,
        now: datetime,
    ) -> None: ...

    @abstractmethod
    async def check_asset_goal(self, *, owner_username: str, now: datetime) -> None: ...
