from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from core.notifications.enums import DeliveryStatus
from core.notifications.finance.schemas import AssetFinanceDelivery, FinanceDelivery


class FinanceDeliveryStorage(ABC):
    @abstractmethod
    async def plan(self, *, now: datetime, limit: int) -> int: ...

    @abstractmethod
    async def claim(
        self,
        *,
        now: datetime,
        lease_until: datetime,
        max_attempts: int,
    ) -> FinanceDelivery | AssetFinanceDelivery | None: ...

    @abstractmethod
    async def refresh(
        self,
        *,
        delivery: FinanceDelivery | AssetFinanceDelivery,
        now: datetime,
    ) -> FinanceDelivery | AssetFinanceDelivery | None: ...

    @abstractmethod
    async def finish(
        self,
        *,
        delivery: FinanceDelivery | AssetFinanceDelivery,
        status: DeliveryStatus,
        now: datetime,
        next_attempt_at: datetime,
    ) -> None: ...

    @abstractmethod
    async def prune(self, *, now: datetime, retention: timedelta) -> int: ...
