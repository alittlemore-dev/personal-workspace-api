from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Self
from zoneinfo import ZoneInfo

from core.events.enums import EventFrequency
from core.events.exceptions import InvalidEventDataError

MAX_EVENT_TITLE_LENGTH = 255
MAX_EVENT_DESCRIPTION_LENGTH = 2000


@dataclass(frozen=True, slots=True, kw_only=True)
class EventRecurrence:
    frequency: EventFrequency
    until_date: date | None


@dataclass(frozen=True, slots=True, kw_only=True)
class EventDraft:
    title: str
    description: str
    anchor_time_zone: ZoneInfo
    all_day: bool
    start: date | datetime
    end: date | datetime
    recurrence: EventRecurrence

    def __post_init__(self) -> None:
        if (
            not self.title.strip()
            or len(self.title) > MAX_EVENT_TITLE_LENGTH
            or len(self.description) > MAX_EVENT_DESCRIPTION_LENGTH
        ):
            raise InvalidEventDataError
        if self.all_day:
            if isinstance(self.start, datetime) or isinstance(self.end, datetime):
                raise InvalidEventDataError
        elif (
            not isinstance(self.start, datetime)
            or not isinstance(self.end, datetime)
            or self.start.tzinfo is None
            or self.end.tzinfo is None
            or self.start.utcoffset() != timedelta(0)
            or self.end.utcoffset() != timedelta(0)
        ):
            raise InvalidEventDataError
        if self.start >= self.end:
            raise InvalidEventDataError
        if (
            self.recurrence.frequency == EventFrequency.NONE
            and self.recurrence.until_date is not None
        ):
            raise InvalidEventDataError
        if self.recurrence.until_date is not None:
            anchor_date = self.start.date() if isinstance(self.start, datetime) else self.start
            if isinstance(self.start, datetime):
                anchor_date = self.start.astimezone(self.anchor_time_zone).date()
            if self.recurrence.until_date < anchor_date:
                raise InvalidEventDataError


@dataclass(frozen=True, slots=True, kw_only=True)
class Event:
    id: str
    title: str
    description: str
    anchor_time_zone: ZoneInfo
    all_day: bool
    start: date | datetime
    end: date | datetime
    recurrence: EventRecurrence

    @classmethod
    def from_draft(cls, *, event_id: str, draft: EventDraft) -> Self:
        return cls(
            id=event_id,
            title=draft.title,
            description=draft.description,
            anchor_time_zone=draft.anchor_time_zone,
            all_day=draft.all_day,
            start=draft.start,
            end=draft.end,
            recurrence=draft.recurrence,
        )

    def occurrence_at(
        self,
        *,
        index: int,
        time_zone: ZoneInfo,
    ) -> tuple[date | datetime, date | datetime]:
        if self.recurrence.frequency == EventFrequency.NONE:
            return self.start, self.end
        if index == 0 and time_zone == self.anchor_time_zone:
            return self.start, self.end
        zone = self.anchor_time_zone
        if isinstance(self.start, datetime) and isinstance(self.end, datetime):
            local_start = self.start.astimezone(zone)
            local_end = self.end.astimezone(zone)
            start_wall = local_start.replace(tzinfo=None)
            end_wall = local_end.replace(tzinfo=None)
            next_start = self._shift_date(value=start_wall, index=index)
            if not isinstance(next_start, datetime):
                raise InvalidEventDataError
            next_end = next_start + (end_wall - start_wall)
            resolved_start = self._resolve_local_time(
                value=next_start,
                original_fold=local_start.fold,
                time_zone=time_zone,
            )
            resolved_end = self._resolve_local_time(
                value=next_end,
                original_fold=local_end.fold,
                time_zone=time_zone,
            )
            if resolved_end <= resolved_start:
                resolved_end = resolved_start + (self.end - self.start)
            return resolved_start, resolved_end
        if isinstance(self.start, date) and isinstance(self.end, date):
            next_start = self._shift_date(value=self.start, index=index)
            return next_start, next_start + (self.end - self.start)
        raise InvalidEventDataError

    def _resolve_local_time(
        self,
        *,
        value: datetime,
        original_fold: int,
        time_zone: ZoneInfo,
    ) -> datetime:
        zone = time_zone
        candidate = value.replace(tzinfo=zone, fold=original_fold).astimezone(UTC)
        if candidate.astimezone(zone).replace(tzinfo=None) == value:
            return candidate
        adjusted = [value.replace(tzinfo=zone, fold=fold).astimezone(UTC) for fold in (0, 1)]
        forward = [
            instant for instant in adjusted if instant.astimezone(zone).replace(tzinfo=None) > value
        ]
        if not forward:
            raise InvalidEventDataError
        return min(
            forward,
            key=lambda instant: instant.astimezone(zone).replace(tzinfo=None),
        )

    def _shift_date(self, *, value: date | datetime, index: int) -> date | datetime:
        frequency = self.recurrence.frequency
        if frequency == EventFrequency.NONE:
            return value
        if frequency == EventFrequency.DAILY:
            return value + timedelta(days=index)
        if frequency == EventFrequency.WEEKLY:
            return value + timedelta(weeks=index)
        if frequency == EventFrequency.MONTHLY:
            month_number = value.year * 12 + value.month - 1 + index
            year, month_zero = divmod(month_number, 12)
            month = month_zero + 1
            return value.replace(
                year=year,
                month=month,
                day=min(value.day, monthrange(year, month)[1]),
            )
        year = value.year + index
        return value.replace(year=year, day=min(value.day, monthrange(year, value.month)[1]))

    def first_candidate_index(self, *, start_date: date) -> int:
        zone = self.anchor_time_zone
        anchor = (
            self.start.astimezone(zone).date() if isinstance(self.start, datetime) else self.start
        )
        end = self.end.astimezone(zone).date() if isinstance(self.end, datetime) else self.end
        earliest = start_date - timedelta(days=max(1, (end - anchor).days + 2))
        delta = (earliest - anchor).days
        if self.recurrence.frequency == EventFrequency.DAILY:
            return max(0, delta)
        if self.recurrence.frequency == EventFrequency.WEEKLY:
            return max(0, delta // 7)
        if self.recurrence.frequency == EventFrequency.MONTHLY:
            return max(0, (earliest.year - anchor.year) * 12 + earliest.month - anchor.month - 1)
        if self.recurrence.frequency == EventFrequency.YEARLY:
            return max(0, earliest.year - anchor.year - 1)
        return 0
