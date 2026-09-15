from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Self

from core.calendar.enums import CalendarEntryKind, CalendarEntryPeriod, CalendarWindow
from core.knowledge.dates.schemas import (
    KnowledgeDateDetails,
    KnowledgeDatePersonLink,
    KnowledgeDateValue,
)
from core.knowledge.items.schemas import KnowledgeItem

if TYPE_CHECKING:
    from core.knowledge.people.schemas import PersonDetails

DECEMBER_MONTH = 12


@dataclass(frozen=True, slots=True, kw_only=True)
class CalendarWindowSelection:
    reference_date: date
    window: CalendarWindow

    @classmethod
    def from_reference_date(
        cls,
        *,
        reference_date: date,
        window: CalendarWindow,
    ) -> Self:
        return cls(reference_date=reference_date, window=window)

    @property
    def months(self) -> tuple[int, ...]:
        if self.window == CalendarWindow.MONTH:
            return (self.reference_date.month,)
        return (self.reference_date.month, self.reference_date.month % DECEMBER_MONTH + 1)

    def period_for(self, *, month: int) -> CalendarEntryPeriod:
        if month == self.reference_date.month:
            return CalendarEntryPeriod.CURRENT_MONTH
        return CalendarEntryPeriod.NEXT_MONTH

    def occurrence_year_for(self, *, month: int) -> int:
        if self.reference_date.month == DECEMBER_MONTH and month == 1:
            return self.reference_date.year + 1
        return self.reference_date.year


@dataclass(frozen=True, slots=True, kw_only=True)
class CalendarAnnualDate:
    day: int
    month: int
    year: int | None

    @classmethod
    def from_knowledge_date_value(cls, *, value: KnowledgeDateValue) -> Self:
        return cls(day=value.day, month=value.month, year=value.year)


@dataclass(frozen=True, slots=True, kw_only=True)
class CalendarBirthdaySource:
    item_id: str
    annual_date: CalendarAnnualDate

    @classmethod
    def from_person_details(cls, *, details: PersonDetails) -> Self | None:
        if details.birthday is None:
            return None
        return cls(
            item_id=details.item_id,
            annual_date=CalendarAnnualDate(
                day=details.birthday.day,
                month=details.birthday.month,
                year=details.birthday.year,
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CalendarSources:
    date_details: list[KnowledgeDateDetails]
    birthdays: list[CalendarBirthdaySource]

    @classmethod
    def from_details(
        cls,
        *,
        date_details: list[KnowledgeDateDetails],
        birthday_details: list[PersonDetails],
    ) -> Self:
        birthdays = [
            source
            for details in birthday_details
            if (source := CalendarBirthdaySource.from_person_details(details=details)) is not None
        ]
        return cls(date_details=list(date_details), birthdays=birthdays)

    @property
    def is_empty(self) -> bool:
        return not self.date_details and not self.birthdays

    @property
    def date_ids(self) -> set[str]:
        return {details.item_id for details in self.date_details}

    def person_ids(self, *, links: list[KnowledgeDatePersonLink]) -> set[str]:
        return {source.item_id for source in self.birthdays} | {link.person_id for link in links}


@dataclass(frozen=True, slots=True, kw_only=True)
class CalendarRelatedPerson:
    id: str
    display_name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CalendarEntry:
    id: str
    kind: CalendarEntryKind
    display_name: str
    annual_date: CalendarAnnualDate
    period: CalendarEntryPeriod
    occurrence_year: int
    related_people: list[CalendarRelatedPerson]

    @classmethod
    def from_memorable_date(
        cls,
        *,
        details: KnowledgeDateDetails,
        item: KnowledgeItem,
        selection: CalendarWindowSelection,
        related_people: list[CalendarRelatedPerson],
    ) -> Self:
        return cls(
            id=details.item_id,
            kind=CalendarEntryKind.MEMORABLE_DATE,
            display_name=item.display_name,
            annual_date=CalendarAnnualDate.from_knowledge_date_value(value=details.date),
            period=selection.period_for(month=details.date.month),
            occurrence_year=selection.occurrence_year_for(month=details.date.month),
            related_people=related_people,
        )

    @classmethod
    def from_birthday(
        cls,
        *,
        source: CalendarBirthdaySource,
        person: KnowledgeItem,
        selection: CalendarWindowSelection,
    ) -> Self:
        return cls(
            id=source.item_id,
            kind=CalendarEntryKind.BIRTHDAY,
            display_name=person.display_name,
            annual_date=source.annual_date,
            period=selection.period_for(month=source.annual_date.month),
            occurrence_year=selection.occurrence_year_for(month=source.annual_date.month),
            related_people=[],
        )

    @property
    def sort_key(self) -> tuple[int, int, int, str, str]:
        period_order = 0 if self.period == CalendarEntryPeriod.CURRENT_MONTH else 1
        kind_order = 0 if self.kind == CalendarEntryKind.MEMORABLE_DATE else 1
        return (
            period_order,
            self.annual_date.day,
            kind_order,
            self.display_name.casefold(),
            self.id,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CalendarSummary:
    memorable_date_count: int
    birthday_count: int

    @classmethod
    def from_entries(cls, *, entries: list[CalendarEntry]) -> Self:
        return cls(
            memorable_date_count=sum(
                entry.kind == CalendarEntryKind.MEMORABLE_DATE for entry in entries
            ),
            birthday_count=sum(entry.kind == CalendarEntryKind.BIRTHDAY for entry in entries),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Calendar:
    reference_date: date
    window: CalendarWindow
    summary: CalendarSummary
    entries: list[CalendarEntry]

    @classmethod
    def empty(cls, *, selection: CalendarWindowSelection) -> Self:
        return cls(
            reference_date=selection.reference_date,
            window=selection.window,
            summary=CalendarSummary(memorable_date_count=0, birthday_count=0),
            entries=[],
        )

    @classmethod
    def from_sources(
        cls,
        *,
        selection: CalendarWindowSelection,
        sources: CalendarSources,
        links: list[KnowledgeDatePersonLink],
        date_items: list[KnowledgeItem],
        people: list[KnowledgeItem],
    ) -> Self:
        date_items_by_id = {item.id: item for item in date_items}
        people_by_id = {person.id: person for person in people}
        related_people_by_date: dict[str, list[CalendarRelatedPerson]] = {
            date_id: [] for date_id in sources.date_ids
        }
        for link in links:
            person = people_by_id[link.person_id]
            related_people_by_date[link.date_id].append(
                CalendarRelatedPerson(id=person.id, display_name=person.display_name),
            )
        for related_people in related_people_by_date.values():
            related_people.sort(key=lambda person: (person.display_name.casefold(), person.id))
        entries = [
            CalendarEntry.from_memorable_date(
                details=details,
                item=date_items_by_id[details.item_id],
                selection=selection,
                related_people=related_people_by_date[details.item_id],
            )
            for details in sources.date_details
        ]
        entries.extend(
            CalendarEntry.from_birthday(
                source=source,
                person=people_by_id[source.item_id],
                selection=selection,
            )
            for source in sources.birthdays
        )
        entries.sort(key=lambda entry: entry.sort_key)
        return cls(
            reference_date=selection.reference_date,
            window=selection.window,
            summary=CalendarSummary.from_entries(entries=entries),
            entries=entries,
        )
