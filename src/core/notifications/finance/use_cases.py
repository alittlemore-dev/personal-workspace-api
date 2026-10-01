from dataclasses import dataclass
from datetime import datetime, timedelta
from time import monotonic

from core.finance.exceptions import FinanceNotFoundError
from core.finance.storages import FinanceStorage
from core.notifications.clients import (
    PermanentReminderSendError,
    ReminderSender,
    RetryableReminderSendError,
)
from core.notifications.enums import DeliveryStatus
from core.notifications.finance.schemas import FinanceDeliveryConfig
from core.notifications.finance.services import FinanceNotificationFormatter
from core.notifications.finance.storages import FinanceDeliveryStorage
from core.telegram.exceptions import TelegramServiceError
from core.telegram.storages import TelegramAccountSettingsReader, TelegramTransaction


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessFinanceNotificationsUseCase:
    storage: FinanceDeliveryStorage
    finance_storage: FinanceStorage
    settings_reader: TelegramAccountSettingsReader
    sender: ReminderSender
    formatter: FinanceNotificationFormatter
    transaction: TelegramTransaction
    config: FinanceDeliveryConfig

    async def run(self, *, now: datetime) -> int:
        started = monotonic()
        started_at = now
        await self.storage.plan(now=now, limit=self.config.batch_size)
        await self.transaction.commit()
        sent = 0
        for _ in range(self.config.batch_size):
            now = started_at + timedelta(seconds=monotonic() - started)
            delivery = await self.storage.claim(
                now=now,
                lease_until=now + self.config.claim_lease,
                max_attempts=self.config.max_attempts,
            )
            await self.transaction.commit()
            if delivery is None:
                break
            status = DeliveryStatus.CANCELED
            next_attempt = now + self.config.retry_interval
            try:
                allowed = await self.settings_reader.can_notify(
                    owner_username=delivery.event.owner_username,
                )
                month = await self.finance_storage.get_month(
                    owner_username=delivery.event.owner_username,
                    now=delivery.event.created_at,
                )
                transaction = await self.finance_storage.get_transaction(
                    owner_username=delivery.event.owner_username,
                    transaction_id=delivery.event.payload.transaction_id,
                    now=delivery.event.created_at,
                )
                now = started_at + timedelta(seconds=monotonic() - started)
                refreshed = await self.storage.refresh(delivery=delivery, now=now)
                if refreshed is None:
                    await self.transaction.commit()
                    continue
                delivery = refreshed
                if delivery.event.expires_at <= now:
                    status = DeliveryStatus.EXPIRED
                elif (
                    delivery.eligible(month)
                    and not transaction.deleted
                    and transaction.version == delivery.event.payload.transaction_version
                    and allowed
                    and delivery.connection is not None
                ):
                    await self.sender.send(
                        private_chat_id=delivery.connection.private_chat_id,
                        text=self.formatter.format(delivery),
                    )
                    status = DeliveryStatus.DONE
                    sent += 1
            except FinanceNotFoundError:
                status = DeliveryStatus.CANCELED
            except PermanentReminderSendError:
                status = DeliveryStatus.FAILED
            except (RetryableReminderSendError, TelegramServiceError) as exc:
                now = started_at + timedelta(seconds=monotonic() - started)
                next_attempt = now + self.config.retry_interval
                status = (
                    DeliveryStatus.RETRY
                    if delivery.attempts < self.config.max_attempts
                    else DeliveryStatus.FAILED
                )
                if isinstance(exc, RetryableReminderSendError):
                    now = started_at + timedelta(seconds=monotonic() - started)
                    next_attempt = now + max(
                        self.config.retry_interval,
                        timedelta(seconds=exc.retry_after_seconds),
                    )
            now = started_at + timedelta(seconds=monotonic() - started)
            await self.storage.finish(
                delivery=delivery,
                status=status,
                now=now,
                next_attempt_at=next_attempt,
            )
            await self.transaction.commit()
        return sent

    async def prune(self, *, now: datetime) -> int:
        count = await self.storage.prune(now=now, retention=self.config.retention)
        await self.transaction.commit()
        return count
