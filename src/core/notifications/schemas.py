from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from core.i18n.enums import LanguageEnum
from core.notifications.enums import ReminderKind


@dataclass(frozen=True, slots=True, kw_only=True)
class ReminderSource:
    owner_username: str
    item_id: str
    kind: ReminderKind
    title: str
    day: int
    month: int
    year: int | None
    description: str
    related_people: tuple[str, ...]
    notifications_enabled: bool

    def occurs_on(self, *, day: date) -> bool:
        return (
            self.notifications_enabled
            and self.month == day.month
            and self.day == day.day
            and (self.year is None or self.year <= day.year)
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ReminderDeliveryKey:
    connection_id: str
    kind: ReminderKind
    item_id: str
    occurrence_date: date
    lead_days: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ReminderDelivery:
    key: ReminderDeliveryKey
    attempts: int
    expires_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class ReminderSchedule:
    scan_batch_size: int
    max_attempts: int
    retry_interval: timedelta
    claim_lease: timedelta
    local_send_time: time


@dataclass(frozen=True, slots=True, kw_only=True)
class ReminderWindow:
    local_date: date
    eligible: bool
    send_at: datetime
    expires_at: datetime

    @classmethod
    def for_connection(
        cls,
        *,
        now: datetime,
        time_zone: str,
        local_send_time: time,
    ) -> ReminderWindow:
        local = now.astimezone(ZoneInfo(time_zone))
        send_at = datetime.combine(local.date(), local_send_time, tzinfo=ZoneInfo(time_zone))
        next_midnight = datetime.combine(
            local.date() + timedelta(days=1),
            time.min,
            tzinfo=ZoneInfo(time_zone),
        )
        return cls(
            local_date=local.date(),
            eligible=local.time() >= local_send_time,
            send_at=send_at.astimezone(UTC),
            expires_at=next_midnight.astimezone(UTC),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ReminderRecipient:
    connection_id: str
    owner_username: str
    private_chat_id: int
    notify_birthday: bool
    notify_memorable_date: bool
    language: LanguageEnum
    time_zone: str

    def subscribes_to(self, *, kind: ReminderKind) -> bool:
        if kind == ReminderKind.BIRTHDAY:
            return self.notify_birthday
        return self.notify_memorable_date
