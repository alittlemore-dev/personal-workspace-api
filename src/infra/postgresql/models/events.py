from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Boolean, Date, Enum, Index, String
from sqlalchemy.orm import Mapped, declared_attr, mapped_column
from sqlalchemy_dev_utils.types.datetime import UTCDateTime

from core.events.enums import EventFrequency
from core.events.schemas import Event, EventDraft, EventRecurrence
from infra.postgresql.models.base import BaseModel, TableArgs
from infra.postgresql.models.mixins.ids import HexUuidIDMixin
from infra.postgresql.types import ZoneInfoType


class EventModel(HexUuidIDMixin, BaseModel):
    __tablename__ = "event_model"

    author_username: Mapped[str] = mapped_column(String(length=255))
    title: Mapped[str] = mapped_column(String(length=255))
    description: Mapped[str] = mapped_column(String(length=2000))
    anchor_time_zone: Mapped[ZoneInfo] = mapped_column(ZoneInfoType())
    all_day: Mapped[bool] = mapped_column(Boolean)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    start_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    end_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    frequency: Mapped[EventFrequency] = mapped_column(
        Enum(
            EventFrequency,
            native_enum=True,
            name="event_frequency_enum",
            values_callable=lambda values: [value.value for value in values],
        ),
    )
    until_date: Mapped[date | None] = mapped_column(Date)

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgs:
        return (Index("event_author_start_idx", cls.author_username, cls.start_at, cls.start_date),)

    @classmethod
    def from_draft(cls, *, draft: EventDraft, author_username: str) -> EventModel:
        return cls(
            author_username=author_username,
            title=draft.title,
            description=draft.description,
            anchor_time_zone=draft.anchor_time_zone,
            all_day=draft.all_day,
            start_date=draft.start if draft.all_day else None,
            end_date=draft.end if draft.all_day else None,
            start_at=draft.start if not draft.all_day else None,
            end_at=draft.end if not draft.all_day else None,
            frequency=draft.recurrence.frequency,
            until_date=draft.recurrence.until_date,
        )

    def update_from_draft(self, *, draft: EventDraft) -> None:
        self.title = draft.title
        self.description = draft.description
        self.anchor_time_zone = draft.anchor_time_zone
        self.all_day = draft.all_day
        self.start_date = (
            draft.start if draft.all_day and not isinstance(draft.start, datetime) else None
        )
        self.end_date = draft.end if draft.all_day and not isinstance(draft.end, datetime) else None
        self.start_at = draft.start if isinstance(draft.start, datetime) else None
        self.end_at = draft.end if isinstance(draft.end, datetime) else None
        self.frequency = draft.recurrence.frequency
        self.until_date = draft.recurrence.until_date

    def to_domain_schema(self) -> Event:
        start = self.start_date if self.all_day else self.start_at
        end = self.end_date if self.all_day else self.end_at
        if start is None or end is None:
            message = "Stored event is missing its time range"
            raise ValueError(message)
        return Event(
            id=self.id,
            title=self.title,
            description=self.description,
            anchor_time_zone=self.anchor_time_zone,
            all_day=self.all_day,
            start=start,
            end=end,
            recurrence=EventRecurrence(frequency=self.frequency, until_date=self.until_date),
        )
