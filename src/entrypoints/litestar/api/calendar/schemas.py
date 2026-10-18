from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import Field

from core.calendar.enums import CalendarEntryKind, CalendarEntryPeriod, CalendarWindow
from core.calendar.occurrences import (
    CalendarOccurrence,
    CalendarOccurrences,
    UnplacedAnnualEntry,
)
from core.calendar.schemas import (
    Calendar,
    CalendarAnnualDate,
    CalendarEntry,
    CalendarRelatedPerson,
    CalendarSummary,
)
from entrypoints.litestar.api.schemas import CamelCaseSchema


class CalendarAnnualDateResponseSchema(CamelCaseSchema):
    day: Annotated[
        int,
        Field(
            title="Day",
            ge=1,
            le=31,
            description=(
                "Day of the month, from 1 to 31; must form a valid date with month and year."
            ),
            examples=[18],
        ),
    ]
    month: Annotated[
        int,
        Field(
            title="Month",
            ge=1,
            le=12,
            description="Calendar month, from 1 to 12.",
            examples=[10],
        ),
    ]
    year: Annotated[
        int | None,
        Field(
            title="Optional first year",
            ge=1,
            le=9999,
            description="Original year; null when the year is unknown.",
            examples=[1992],
        ),
    ]

    @classmethod
    def from_domain_schema(
        cls,
        *,
        schema: CalendarAnnualDate,
    ) -> CalendarAnnualDateResponseSchema:
        return cls.model_construct(day=schema.day, month=schema.month, year=schema.year)


class CalendarRelatedPersonResponseSchema(CamelCaseSchema):
    id: Annotated[
        str,
        Field(
            title="Identifier",
            description="Opaque resource identifier; use the value returned by this API.",
            examples=["4e92d4de561f4bc7a3eed227868952db"],
        ),
    ]
    display_name: Annotated[
        str,
        Field(
            title="Display name",
            description="Human-readable display name.",
            examples=["Alex Morgan"],
        ),
    ]

    @classmethod
    def from_domain_schema(
        cls,
        *,
        schema: CalendarRelatedPerson,
    ) -> CalendarRelatedPersonResponseSchema:
        return cls.model_construct(id=schema.id, display_name=schema.display_name)


class CalendarEntryResponseSchema(CamelCaseSchema):
    id: Annotated[
        str,
        Field(
            title="Identifier",
            description="Opaque resource identifier; use the value returned by this API.",
            examples=["4e92d4de561f4bc7a3eed227868952db"],
        ),
    ]
    kind: Annotated[
        CalendarEntryKind,
        Field(
            title="Entry kind",
            description="Kind; allowed values are listed in the referenced enumeration.",
            examples=["birthday"],
        ),
    ]
    display_name: Annotated[
        str,
        Field(
            title="Display name",
            description="Human-readable display name.",
            examples=["Alex Morgan"],
        ),
    ]
    annual_date: Annotated[
        CalendarAnnualDateResponseSchema,
        Field(
            title="Annual date",
            description=("Annual date; see the nested schema for its fields."),
        ),
    ]
    period: Annotated[
        CalendarEntryPeriod,
        Field(
            title="Calendar period",
            description="Period; allowed values are listed in the referenced enumeration.",
            examples=["currentMonth"],
        ),
    ]
    occurrence_year: Annotated[
        int,
        Field(
            title="Occurrence year",
            description="Year of this occurrence of the annual date.",
            examples=[2026],
        ),
    ]
    related_people: Annotated[
        list[CalendarRelatedPersonResponseSchema],
        Field(title="People", description="Related people returned by this operation."),
    ]

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
    memorable_date_count: Annotated[
        int,
        Field(
            title="Memorable date count",
            ge=0,
            description="Number of memorable dates in this calendar window.",
            examples=[4],
        ),
    ]
    birthday_count: Annotated[
        int,
        Field(
            title="Birthday count",
            ge=0,
            description="Number of birthdays in this calendar window.",
            examples=[2],
        ),
    ]

    @classmethod
    def from_domain_schema(cls, *, schema: CalendarSummary) -> CalendarSummaryResponseSchema:
        return cls.model_construct(
            memorable_date_count=schema.memorable_date_count,
            birthday_count=schema.birthday_count,
        )


class CalendarResponseSchema(CamelCaseSchema):
    reference_date: Annotated[
        date,
        Field(
            title="Browser-local reference date",
            description="Browser-local reference date for the calendar window.",
            examples=["2026-10-18"],
        ),
    ]
    window: Annotated[
        CalendarWindow,
        Field(
            title="Calendar window",
            description="Window; allowed values are listed in the referenced enumeration.",
            examples=["month"],
        ),
    ]
    summary: Annotated[
        CalendarSummaryResponseSchema,
        Field(
            title="Calendar summary",
            description="Counts of birthdays and memorable dates in this window.",
            examples=[{"memorableDateCount": 4, "birthdayCount": 2}],
        ),
    ]
    entries: Annotated[
        list[CalendarEntryResponseSchema],
        Field(title="Entries", description="Entries returned by this operation."),
    ]

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


class CalendarOccurrenceResponseSchema(CamelCaseSchema):
    id: str = Field(
        description="Opaque resource identifier; use the value returned by this API.",
        examples=["4e92d4de561f4bc7a3eed227868952db"],
    )
    source_id: str = Field(
        description="Identifier of the source event, person, or memorable date.",
        examples=["4e92d4de561f4bc7a3eed227868952db"],
    )
    kind: str = Field(
        description="Occurrence source kind: event, birthday, or memorableDate.",
        examples=["event"],
    )
    display_name: str = Field(description="Human-readable display name.", examples=["Alex Morgan"])
    all_day: bool = Field(
        description=(
            "True for calendar-date intervals; false for timestamps with explicit UTC offsets."
        ),
        examples=[False],
    )
    start: str = Field(description="Inclusive interval start.", examples=["2026-10-18T09:00:00Z"])
    end: str = Field(
        description="Exclusive interval end; must follow start.",
        examples=["2026-10-18T10:00:00Z"],
    )
    annual_date: CalendarAnnualDateResponseSchema | None = Field(
        description="Annual date; see the nested schema for its fields.",
    )
    related_people: list[CalendarRelatedPersonResponseSchema] = Field(
        description="Related people returned by this operation.",
    )

    @classmethod
    def from_domain_schema(cls, *, schema: CalendarOccurrence) -> CalendarOccurrenceResponseSchema:
        return cls.model_construct(
            id=schema.id,
            source_id=schema.source_id,
            kind=schema.kind,
            display_name=schema.display_name,
            all_day=schema.all_day,
            start=schema.start.isoformat().replace("+00:00", "Z"),
            end=schema.end.isoformat().replace("+00:00", "Z"),
            annual_date=(
                CalendarAnnualDateResponseSchema.from_domain_schema(schema=schema.annual_date)
                if schema.annual_date is not None
                else None
            ),
            related_people=[
                CalendarRelatedPersonResponseSchema.from_domain_schema(schema=person)
                for person in schema.related_people
            ],
        )


class UnplacedAnnualEntryResponseSchema(CamelCaseSchema):
    source_id: str = Field(
        description="Identifier of the source event, person, or memorable date.",
        examples=["4e92d4de561f4bc7a3eed227868952db"],
    )
    kind: CalendarEntryKind = Field(
        description="Kind; allowed values are listed in the referenced enumeration.",
        examples=["birthday"],
    )
    display_name: str = Field(description="Human-readable display name.", examples=["Alex Morgan"])
    annual_date: CalendarAnnualDateResponseSchema = Field(
        description="Annual date; see the nested schema for its fields.",
    )
    related_people: list[CalendarRelatedPersonResponseSchema] = Field(
        description="Related people returned by this operation.",
    )

    @classmethod
    def from_domain_schema(
        cls,
        *,
        schema: UnplacedAnnualEntry,
    ) -> UnplacedAnnualEntryResponseSchema:
        return cls.model_construct(
            source_id=schema.source_id,
            kind=schema.kind,
            display_name=schema.display_name,
            annual_date=CalendarAnnualDateResponseSchema.from_domain_schema(
                schema=schema.annual_date,
            ),
            related_people=[
                CalendarRelatedPersonResponseSchema.from_domain_schema(schema=person)
                for person in schema.related_people
            ],
        )


class CalendarOccurrencesResponseSchema(CamelCaseSchema):
    entries: list[CalendarOccurrenceResponseSchema] = Field(
        description="Entries returned by this operation.",
    )
    unplaced_annual_entries: list[UnplacedAnnualEntryResponseSchema] = Field(
        description="Unplaced annual entries returned by this operation.",
    )

    @classmethod
    def from_domain_schema(
        cls,
        *,
        schema: CalendarOccurrences,
    ) -> CalendarOccurrencesResponseSchema:
        return cls.model_construct(
            entries=[
                CalendarOccurrenceResponseSchema.from_domain_schema(schema=entry)
                for entry in schema.entries
            ],
            unplaced_annual_entries=[
                UnplacedAnnualEntryResponseSchema.from_domain_schema(schema=entry)
                for entry in schema.unplaced_annual_entries
            ],
        )
