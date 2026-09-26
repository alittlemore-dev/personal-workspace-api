from dataclasses import dataclass
from datetime import datetime, timedelta

from core.notifications.clients import (
    PermanentReminderSendError,
    RetryableReminderSendError,
)
from core.notifications.enums import ReminderKind
from core.notifications.schemas import (
    ReminderDelivery,
    ReminderDeliveryKey,
    ReminderRecipient,
    ReminderSchedule,
    ReminderWindow,
)
from core.notifications.services import ReminderDeliveryService
from core.notifications.storages import ReminderStorage
from core.telegram.exceptions import TelegramServiceError
from core.telegram.storages import TelegramTransaction


@dataclass(frozen=True, slots=True, kw_only=True)
class PlanRemindersUseCase:
    storage: ReminderStorage
    transaction: TelegramTransaction
    schedule: ReminderSchedule

    async def run(self, *, now: datetime) -> int:
        planned = 0
        after_id = ""
        while True:
            recipients = await self.storage.list_recipients(
                after_id=after_id,
                limit=self.schedule.scan_batch_size,
            )
            if not recipients:
                break
            for recipient in recipients:
                after_id = recipient.connection_id
                planned += await self._plan_recipient(recipient=recipient, now=now)
                await self.transaction.commit()
            if len(recipients) < self.schedule.scan_batch_size:
                break
        return planned

    async def _plan_recipient(self, *, recipient: ReminderRecipient, now: datetime) -> int:
        window = ReminderWindow.for_connection(
            now=now,
            time_zone=recipient.time_zone,
            local_send_time=self.schedule.local_send_time,
        )
        planned = 0
        for lead_days in (7, 1):
            for kind in (ReminderKind.BIRTHDAY, ReminderKind.MEMORABLE_DATE):
                if recipient.subscribes_to(kind=kind):
                    planned += await self._plan_kind(
                        recipient=recipient,
                        window=window,
                        kind=kind,
                        lead_days=lead_days,
                        now=now,
                    )
        return planned

    async def _plan_kind(
        self,
        *,
        recipient: ReminderRecipient,
        window: ReminderWindow,
        kind: ReminderKind,
        lead_days: int,
        now: datetime,
    ) -> int:
        occurrence_date = window.local_date + timedelta(days=lead_days)
        sources = await self.storage.list_sources(
            owner_username=recipient.owner_username,
            kind=kind,
            occurrence_date=occurrence_date,
        )
        planned = 0
        for source in sources:
            if not source.occurs_on(day=occurrence_date):
                continue
            key = ReminderDeliveryKey(
                connection_id=recipient.connection_id,
                kind=kind,
                item_id=source.item_id,
                occurrence_date=occurrence_date,
                lead_days=lead_days,
            )
            if await self.storage.plan(
                key=key,
                now=now,
                send_at=window.send_at,
                expires_at=window.expires_at,
            ):
                planned += 1
        return planned


@dataclass(frozen=True, slots=True, kw_only=True)
class SendRemindersUseCase:
    storage: ReminderStorage
    delivery_service: ReminderDeliveryService
    transaction: TelegramTransaction
    schedule: ReminderSchedule

    async def run(self, *, now: datetime) -> int:
        sent = 0
        for _ in range(self.schedule.scan_batch_size):
            delivery = await self.storage.claim_due(
                now=now,
                lease_until=now + self.schedule.claim_lease,
                max_attempts=self.schedule.max_attempts,
            )
            await self.transaction.commit()
            if delivery is None:
                break
            sent += await self._send_delivery(delivery=delivery, now=now)
            await self.transaction.commit()
        return sent

    async def _send_delivery(self, *, delivery: ReminderDelivery, now: datetime) -> int:
        key = delivery.key
        current = await self.storage.get_current(
            key=key,
            now=now,
            local_send_time=self.schedule.local_send_time,
        )
        if current is None:
            await self.storage.mark_canceled(key=key, now=now)
            return 0
        try:
            delivered = await self.delivery_service.deliver(
                recipient=current[0],
                source=current[1],
                key=key,
            )
        except TelegramServiceError:
            await self._retry_or_finish(delivery=delivery, now=now)
            return 0
        except PermanentReminderSendError:
            await self.storage.mark_failed(key=key, now=now)
        except RetryableReminderSendError as exc:
            await self._retry_or_finish(
                delivery=delivery,
                now=now,
                retry_after=timedelta(seconds=exc.retry_after_seconds),
            )
        else:
            if delivered:
                await self.storage.mark_done(key=key, now=now)
                return 1
            await self.storage.mark_canceled(key=key, now=now)
        return 0

    async def _retry_or_finish(
        self,
        *,
        delivery: ReminderDelivery,
        now: datetime,
        retry_after: timedelta | None = None,
    ) -> None:
        if delivery.attempts >= self.schedule.max_attempts:
            await self.storage.mark_failed(key=delivery.key, now=now)
            return
        next_attempt_at = now + max(self.schedule.retry_interval, retry_after or timedelta())
        if next_attempt_at >= delivery.expires_at:
            await self.storage.mark_expired(key=delivery.key, now=now)
            return
        await self.storage.mark_retry(
            key=delivery.key,
            now=now,
            next_attempt_at=next_attempt_at,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PruneRemindersUseCase:
    storage: ReminderStorage
    transaction: TelegramTransaction
    retention: timedelta

    async def run(self, *, now: datetime) -> int:
        removed = await self.storage.expire_and_prune(now=now, retention=self.retention)
        await self.transaction.commit()
        return removed
