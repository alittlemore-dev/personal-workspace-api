from datetime import date
from typing import Annotated, Self
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator

from core.events.enums import EventFrequency
from core.events.schemas import Event, EventDraft, EventRecurrence
from entrypoints.litestar.api.events.validators import parse_event_interval, validate_event_interval
from entrypoints.litestar.api.schemas import CamelCaseSchema
from entrypoints.litestar.api.validation import RequiredShortText


class EventRecurrenceSchema(CamelCaseSchema):
    frequency: EventFrequency
    until_date: date | None

    def to_domain_schema(self) -> EventRecurrence:
        return EventRecurrence(frequency=self.frequency, until_date=self.until_date)

    @classmethod
    def from_domain_schema(cls, *, schema: EventRecurrence) -> EventRecurrenceSchema:
        return cls.model_construct(frequency=schema.frequency, until_date=schema.until_date)


class EventRequestSchema(CamelCaseSchema):
    title: RequiredShortText
    description: Annotated[str, Field(max_length=2000)] = ""
    all_day: bool
    start: str
    end: str
    recurrence: EventRecurrenceSchema

    @model_validator(mode="after")
    def validate_event(self) -> Self:  # noqa: N804
        validate_event_interval(
            all_day=self.all_day,
            start=self.start,
            end=self.end,
            frequency=self.recurrence.frequency,
            until_date=self.recurrence.until_date,
        )
        return self

    def to_domain_schema(self, *, anchor_time_zone: ZoneInfo) -> EventDraft:
        start, end = parse_event_interval(all_day=self.all_day, start=self.start, end=self.end)
        return EventDraft(
            title=self.title,
            description=self.description,
            anchor_time_zone=anchor_time_zone,
            all_day=self.all_day,
            start=start,
            end=end,
            recurrence=self.recurrence.to_domain_schema(),
        )


class EventResponseSchema(CamelCaseSchema):
    id: str
    title: str
    description: str
    all_day: bool
    start: str
    end: str
    recurrence: EventRecurrenceSchema

    @classmethod
    def from_domain_schema(
        cls,
        *,
        schema: Event,
        account_time_zone: ZoneInfo,
    ) -> EventResponseSchema:
        start, end = schema.occurrence_at(index=0, time_zone=account_time_zone)
        return cls.model_construct(
            id=schema.id,
            title=schema.title,
            description=schema.description,
            all_day=schema.all_day,
            start=start.isoformat().replace("+00:00", "Z"),
            end=end.isoformat().replace("+00:00", "Z"),
            recurrence=EventRecurrenceSchema.from_domain_schema(schema=schema.recurrence),
        )


class EventsResponseSchema(CamelCaseSchema):
    events: list[EventResponseSchema]

    @classmethod
    def from_domain_schema(
        cls,
        *,
        events: list[Event],
        account_time_zone: ZoneInfo,
    ) -> EventsResponseSchema:
        return cls.model_construct(
            events=[
                EventResponseSchema.from_domain_schema(
                    schema=event,
                    account_time_zone=account_time_zone,
                )
                for event in events
            ],
        )
