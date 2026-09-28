from dataclasses import dataclass
from datetime import datetime, timedelta

from core.account_time_zone.clients import (
    AccountTimeZoneReader,
    AccountTimeZoneUnavailableError,
)
from core.notifications.schemas import ReminderSchedule
from core.notifications.services import (
    ReminderPlanningService,
    ReminderProcessingService,
)
from core.notifications.storages import ReminderStorage
from core.telegram.storages import TelegramTransaction


@dataclass(frozen=True, slots=True, kw_only=True)
class PlanRemindersUseCase:
    storage: ReminderStorage
    transaction: TelegramTransaction
    schedule: ReminderSchedule
    account_time_zone_reader: AccountTimeZoneReader

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
                try:
                    time_zone = await self.account_time_zone_reader.get_time_zone(
                        owner_username=recipient.owner_username,
                    )
                except AccountTimeZoneUnavailableError:
                    continue
                planned += await ReminderPlanningService(
                    storage=self.storage,
                    schedule=self.schedule,
                ).plan_recipient(
                    recipient=recipient,
                    now=now,
                    time_zone=time_zone,
                )
                await self.transaction.commit()
            if len(recipients) < self.schedule.scan_batch_size:
                break
        return planned


@dataclass(frozen=True, slots=True, kw_only=True)
class SendRemindersUseCase:
    storage: ReminderStorage
    processing_service: ReminderProcessingService
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
            sent += await self.processing_service.send_delivery(delivery=delivery, now=now)
            await self.transaction.commit()
        return sent


@dataclass(frozen=True, slots=True, kw_only=True)
class PruneRemindersUseCase:
    storage: ReminderStorage
    transaction: TelegramTransaction
    retention: timedelta

    async def run(self, *, now: datetime) -> int:
        removed = await self.storage.expire_and_prune(now=now, retention=self.retention)
        await self.transaction.commit()
        return removed
