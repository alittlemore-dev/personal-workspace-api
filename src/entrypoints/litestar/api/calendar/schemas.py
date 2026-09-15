from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import Field

from core.calendar.enums import CalendarEntryKind, CalendarEntryPeriod, CalendarWindow
from core.calendar.schemas import (
    Calendar,
    CalendarAnnualDate,
    CalendarEntry,
    CalendarRelatedPerson,
    CalendarSummary,
)
from entrypoints.litestar.api.schemas import CamelCaseSchema


class CalendarAnnualDateResponseSchema(CamelCaseSchema):
    day: Annotated[int, Field(title="Day", ge=1, le=31)]
    month: Annotated[int, Field(title="Month", ge=1, le=12)]
    year: Annotated[int | None, Field(title="Optional first year", ge=1, le=9999)]

    @classmethod
    def from_domain_schema(
        cls,
        *,
        schema: CalendarAnnualDate,
    ) -> CalendarAnnualDateResponseSchema:
        return cls.model_construct(day=schema.day, month=schema.month, year=schema.year)


class CalendarRelatedPersonResponseSchema(CamelCaseSchema):
    id: Annotated[str, Field(title="Identifier")]
    display_name: Annotated[str, Field(title="Display name")]

    @classmethod
    def from_domain_schema(
        cls,
        *,
        schema: CalendarRelatedPerson,
    ) -> CalendarRelatedPersonResponseSchema:
        return cls.model_construct(id=schema.id, display_name=schema.display_name)


class CalendarEntryResponseSchema(CamelCaseSchema):
    id: Annotated[str, Field(title="Identifier")]
    kind: Annotated[CalendarEntryKind, Field(title="Entry kind")]
    display_name: Annotated[str, Field(title="Display name")]
    annual_date: Annotated[CalendarAnnualDateResponseSchema, Field(title="Annual date")]
    period: Annotated[CalendarEntryPeriod, Field(title="Calendar period")]
    occurrence_year: Annotated[int, Field(title="Occurrence year")]
    related_people: Annotated[list[CalendarRelatedPersonResponseSchema], Field(title="People")]

    @classmethod
    def from_domain_schema(cls, *, schema: CalendarEntry) -> CalendarEntryResponseSchema:
        return cls.model_construct(
            id=schema.id,
            kind=schema.kind,
            display_name=schema.display_name,
            annual_date=CalendarAnnualDateResponseSchema.from_domain_schema(
                schema=schema.annual_date,
            ),
            period=schema.period,
            occurrence_year=schema.occurrence_year,
            related_people=[
                CalendarRelatedPersonResponseSchema.from_domain_schema(schema=person)
                for person in schema.related_people
            ],
        )


class CalendarSummaryResponseSchema(CamelCaseSchema):
    memorable_date_count: Annotated[int, Field(title="Memorable date count", ge=0)]
    birthday_count: Annotated[int, Field(title="Birthday count", ge=0)]

    @classmethod
    def from_domain_schema(cls, *, schema: CalendarSummary) -> CalendarSummaryResponseSchema:
        return cls.model_construct(
            memorable_date_count=schema.memorable_date_count,
            birthday_count=schema.birthday_count,
        )


class CalendarResponseSchema(CamelCaseSchema):
    reference_date: Annotated[date, Field(title="Browser-local reference date")]
    window: Annotated[CalendarWindow, Field(title="Calendar window")]
    summary: Annotated[CalendarSummaryResponseSchema, Field(title="Calendar summary")]
    entries: Annotated[list[CalendarEntryResponseSchema], Field(title="Entries")]

    @classmethod
    def from_domain_schema(cls, *, schema: Calendar) -> CalendarResponseSchema:
        return cls.model_construct(
            reference_date=schema.reference_date,
            window=schema.window,
            summary=CalendarSummaryResponseSchema.from_domain_schema(
                schema=schema.summary,
            ),
            entries=[
                CalendarEntryResponseSchema.from_domain_schema(schema=entry)
                for entry in schema.entries
            ],
        )
