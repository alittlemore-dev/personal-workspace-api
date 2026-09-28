import html
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from core.account_time_zone.clients import (
    AccountTimeZoneReader,
    AccountTimeZoneUnavailableError,
)
from core.i18n.enums import LanguageEnum
from core.notifications.clients import (
    PermanentReminderSendError,
    ReminderSender,
    RetryableReminderSendError,
)
from core.notifications.enums import ReminderKind
from core.notifications.schemas import (
    ReminderDelivery,
    ReminderDeliveryKey,
    ReminderRecipient,
    ReminderSchedule,
    ReminderSource,
    ReminderWindow,
)
from core.notifications.storages import ReminderStorage
from core.telegram.exceptions import TelegramServiceError
from core.telegram.storages import TelegramAccountSettingsReader

WEEK_LEAD_DAYS = 7


class DescriptionTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


@dataclass(frozen=True, slots=True, kw_only=True)
class ReminderTextFormatter:
    description_limit: int

    def description_excerpt(self, *, markdown: str) -> str:
        without_links = re.sub(r"!?\[([^\]]+)\]\([^)]*\)", r"\1", markdown)
        parser = DescriptionTextParser()
        parser.feed(without_links)
        without_markup = re.sub(r"[`*_~>#]+", " ", " ".join(parser.parts))
        value = " ".join(html.unescape(without_markup).split())
        return value[: self.description_limit].rstrip()

    def format(
        self,
        *,
        source: ReminderSource,
        occurrence_date: date,
        lead_days: int,
        language: LanguageEnum,
    ) -> str:
        when = occurrence_date.strftime("%d.%m.%Y")
        excerpt = self.description_excerpt(markdown=source.description)
        if language == LanguageEnum.RU:
            heading = (
                f"Через {lead_days} дн. · {when}"
                if lead_days == WEEK_LEAD_DAYS
                else f"Завтра · {when}"
            )
            if source.kind == ReminderKind.BIRTHDAY:
                age = f" (исполнится {occurrence_date.year - source.year})" if source.year else ""
                return f"{heading}\nДень рождения: {source.title}{age}"
            people = (
                f"\nСвязанные люди: {', '.join(source.related_people)}"
                if source.related_people
                else ""
            )
            anniversary = (
                f"\nГодовщина: {occurrence_date.year - source.year} лет"
                if source.year and occurrence_date.year > source.year
                else ""
            )
            description = f"\n{excerpt}" if excerpt else ""
            return f"{heading}\nПамятная дата: {source.title}{people}{anniversary}{description}"
        heading = (
            f"In {lead_days} days · {when}" if lead_days == WEEK_LEAD_DAYS else f"Tomorrow · {when}"
        )
        if source.kind == ReminderKind.BIRTHDAY:
            age = f" (turning {occurrence_date.year - source.year})" if source.year else ""
            return f"{heading}\nBirthday: {source.title}{age}"
        people = (
            f"\nRelated people: {', '.join(source.related_people)}" if source.related_people else ""
        )
        anniversary = (
            f"\nAnniversary: {occurrence_date.year - source.year} years"
            if source.year and occurrence_date.year > source.year
            else ""
        )
        description = f"\n{excerpt}" if excerpt else ""
        return f"{heading}\nMemorable date: {source.title}{people}{anniversary}{description}"


@dataclass(frozen=True, slots=True, kw_only=True)
class ReminderDeliveryService:
    settings_reader: TelegramAccountSettingsReader
    sender: ReminderSender
    formatter: ReminderTextFormatter

    async def deliver(
        self,
        *,
        recipient: ReminderRecipient,
        source: ReminderSource,
        key: ReminderDeliveryKey,
    ) -> bool:
        if not await self.settings_reader.can_notify(owner_username=recipient.owner_username):
            return False
        message = self.formatter.format(
            source=source,
            occurrence_date=key.occurrence_date,
            lead_days=key.lead_days,
            language=recipient.language,
        )
        await self.sender.send(private_chat_id=recipient.private_chat_id, text=message)
        return True


@dataclass(frozen=True, slots=True, kw_only=True)
class ReminderPlanningService:
    storage: ReminderStorage
    schedule: ReminderSchedule

    async def plan_recipient(
        self,
        *,
        recipient: ReminderRecipient,
        now: datetime,
        time_zone: ZoneInfo,
    ) -> int:
        window = ReminderWindow.for_account(
            now=now,
            time_zone=time_zone,
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
class ReminderProcessingService:
    storage: ReminderStorage
    delivery_service: ReminderDeliveryService
    schedule: ReminderSchedule
    account_time_zone_reader: AccountTimeZoneReader

    async def send_delivery(  # noqa: PLR0911
        self,
        *,
        delivery: ReminderDelivery,
        now: datetime,
    ) -> int:
        key = delivery.key
        recipient = await self.storage.get_recipient(connection_id=key.connection_id)
        if recipient is None:
            await self.storage.mark_canceled(key=key, now=now)
            return 0
        try:
            time_zone = await self.account_time_zone_reader.get_time_zone(
                owner_username=recipient.owner_username,
            )
        except AccountTimeZoneUnavailableError:
            await self._defer_account_unavailable(delivery=delivery, now=now)
            return 0
        window = ReminderWindow.for_account(
            now=now,
            time_zone=time_zone,
            local_send_time=self.schedule.local_send_time,
        )
        if window.local_date + timedelta(days=key.lead_days) != key.occurrence_date:
            await self.storage.mark_canceled(key=key, now=now)
            return 0
        if delivery.scheduled_at != window.send_at or delivery.expires_at != window.expires_at:
            await self.storage.reschedule(
                key=key,
                now=now,
                send_at=window.send_at,
                expires_at=window.expires_at,
            )
            return 0
        current = await self.storage.get_current(
            key=key,
            now=now,
            local_send_time=self.schedule.local_send_time,
            time_zone=time_zone,
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
            await self._defer_account_unavailable(delivery=delivery, now=now)
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

    async def _defer_account_unavailable(
        self,
        *,
        delivery: ReminderDelivery,
        now: datetime,
    ) -> None:
        next_attempt_at = now + self.schedule.retry_interval
        if next_attempt_at >= delivery.expires_at:
            await self.storage.mark_expired(key=delivery.key, now=now)
            return
        await self.storage.defer_without_attempt(
            key=delivery.key,
            now=now,
            next_attempt_at=next_attempt_at,
        )

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
