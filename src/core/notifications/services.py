import html
import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser

from core.i18n.enums import LanguageEnum
from core.notifications.clients import ReminderSender
from core.notifications.enums import ReminderKind
from core.notifications.schemas import ReminderDeliveryKey, ReminderRecipient, ReminderSource
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
