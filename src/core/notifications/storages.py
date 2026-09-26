from abc import ABC, abstractmethod
from datetime import date, datetime, time, timedelta

from core.notifications.enums import ReminderKind
from core.notifications.schemas import (
    ReminderDelivery,
    ReminderDeliveryKey,
    ReminderRecipient,
    ReminderSource,
)


class ReminderStorage(ABC):
    @abstractmethod
    async def list_recipients(self, *, after_id: str, limit: int) -> list[ReminderRecipient]: ...

    @abstractmethod
    async def list_sources(
        self,
        *,
        owner_username: str,
        kind: ReminderKind,
        occurrence_date: date,
    ) -> list[ReminderSource]: ...

    @abstractmethod
    async def plan(
        self,
        *,
        key: ReminderDeliveryKey,
        now: datetime,
        send_at: datetime,
        expires_at: datetime,
    ) -> bool: ...

    @abstractmethod
    async def claim_due(
        self,
        *,
        now: datetime,
        lease_until: datetime,
        max_attempts: int,
    ) -> ReminderDelivery | None: ...

    @abstractmethod
    async def mark_done(self, *, key: ReminderDeliveryKey, now: datetime) -> None: ...

    @abstractmethod
    async def mark_canceled(self, *, key: ReminderDeliveryKey, now: datetime) -> None: ...

    @abstractmethod
    async def mark_expired(self, *, key: ReminderDeliveryKey, now: datetime) -> None: ...

    @abstractmethod
    async def mark_failed(self, *, key: ReminderDeliveryKey, now: datetime) -> None: ...

    @abstractmethod
    async def mark_retry(
        self,
        *,
        key: ReminderDeliveryKey,
        now: datetime,
        next_attempt_at: datetime,
    ) -> None: ...

    @abstractmethod
    async def expire_and_prune(self, *, now: datetime, retention: timedelta) -> int: ...

    @abstractmethod
    async def get_current(
        self,
        *,
        key: ReminderDeliveryKey,
        now: datetime,
        local_send_time: time,
    ) -> tuple[ReminderRecipient, ReminderSource] | None: ...
