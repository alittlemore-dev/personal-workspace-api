from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from core.account_time_zone.clients import AccountTimeZoneReader
from core.calendar.enums import CalendarEntryKind
from core.calendar.schemas import (
    CalendarAnnualDate,
    CalendarRelatedPerson,
    CalendarSources,
    GetCalendarOccurrencesParams,
)
from core.events.schemas import Event
from core.events.storages import EventsStorage
from core.knowledge.dates.storages import KnowledgeDatesStorage
from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.items.storages import KnowledgeItemsStorage
from core.knowledge.people.storages import PeopleStorage


@dataclass(frozen=True, slots=True, kw_only=True)
class CalendarOccurrence:
    id: str
    source_id: str
    kind: str
    display_name: str
    all_day: bool
    start: date | datetime
    end: date | datetime
    annual_date: CalendarAnnualDate | None
    related_people: list[CalendarRelatedPerson]

    def sort_key(self, *, zone: ZoneInfo) -> tuple[datetime, str]:
        if isinstance(self.start, datetime):
            return self.start.astimezone(UTC), self.id
        return datetime.combine(self.start, time.min, zone).astimezone(UTC), self.id


@dataclass(frozen=True, slots=True, kw_only=True)
class UnplacedAnnualEntry:
    source_id: str
    kind: CalendarEntryKind
    display_name: str
    annual_date: CalendarAnnualDate
    related_people: list[CalendarRelatedPerson]


@dataclass(frozen=True, slots=True, kw_only=True)
class CalendarOccurrences:
    entries: list[CalendarOccurrence]
    unplaced_annual_entries: list[UnplacedAnnualEntry]

    def add_event(  # noqa: PLR0913
        self,
        *,
        event: Event,
        start_date: date,
        end_date: date,
        start_boundary: datetime,
        end_boundary: datetime,
        account_zone: ZoneInfo,
    ) -> None:
        index = event.first_candidate_index(
            start_date=start_boundary.astimezone(account_zone).date(),
        )
        while True:
            try:
                occurrence_start, occurrence_end = event.occurrence_at(
                    index=index,
                    time_zone=account_zone,
                )
            except ValueError, OverflowError:
                break
            local_start_date = (
                occurrence_start.astimezone(account_zone).date()
                if isinstance(occurrence_start, datetime)
                else occurrence_start
            )
            if event.all_day and occurrence_start >= end_date:
                break
            if not event.all_day and occurrence_start >= end_boundary:
                break
            if (
                event.recurrence.until_date is not None
                and local_start_date > event.recurrence.until_date
            ):
                break
            if event.all_day:
                overlaps = occurrence_start < end_date and occurrence_end > start_date
            else:
                overlaps = occurrence_start < end_boundary and occurrence_end > start_boundary
            if overlaps:
                self.entries.append(
                    CalendarOccurrence(
                        id=f"{event.id}:{occurrence_start.isoformat()}",
                        source_id=event.id,
                        kind="event",
                        display_name=event.title,
                        all_day=event.all_day,
                        start=occurrence_start,
                        end=occurrence_end,
                        annual_date=None,
                        related_people=[],
                    ),
                )
            if event.recurrence.frequency.value == "none":
                break
            index += 1

    def add_annual(  # noqa: PLR0913
        self,
        *,
        source_id: str,
        kind: CalendarEntryKind,
        display_name: str,
        annual_date: CalendarAnnualDate,
        related_people: list[CalendarRelatedPerson],
        start_date: date,
        end_date: date,
    ) -> None:
        for year in range(start_date.year, end_date.year + 1):
            if annual_date.day > monthrange(year, annual_date.month)[1]:
                february_start = date(year, 2, 1)
                march_start = date(year, 3, 1)
                if (
                    start_date < march_start
                    and end_date > february_start
                    and not any(
                        item.source_id == source_id and item.kind == kind
                        for item in self.unplaced_annual_entries
                    )
                ):
                    self.unplaced_annual_entries.append(
                        UnplacedAnnualEntry(
                            source_id=source_id,
                            kind=kind,
                            display_name=display_name,
                            annual_date=annual_date,
                            related_people=related_people,
                        ),
                    )
                continue
            occurrence_date = date(year, annual_date.month, annual_date.day)
            if start_date <= occurrence_date < end_date:
                self.entries.append(
                    CalendarOccurrence(
                        id=f"{kind.value}:{source_id}:{occurrence_date.isoformat()}",
                        source_id=source_id,
                        kind=kind.value,
                        display_name=display_name,
                        all_day=True,
                        start=occurrence_date,
                        end=occurrence_date + timedelta(days=1),
                        annual_date=annual_date,
                        related_people=related_people,
                    ),
                )


@dataclass(frozen=True, slots=True, kw_only=True)
class CalendarOccurrencesUseCase:
    item_storage: KnowledgeItemsStorage
    dates_storage: KnowledgeDatesStorage
    people_storage: PeopleStorage
    events_storage: EventsStorage
    account_time_zone_reader: AccountTimeZoneReader

    async def get_occurrences(self, *, params: GetCalendarOccurrencesParams) -> CalendarOccurrences:
        account_zone = await self.account_time_zone_reader.get_time_zone(
            owner_username=params.author_username,
        )
        start_boundary = datetime.combine(params.start_date, time.min, account_zone).astimezone(UTC)
        end_boundary = datetime.combine(params.end_date, time.min, account_zone).astimezone(UTC)
        occurrences = CalendarOccurrences(entries=[], unplaced_annual_entries=[])
        for event in await self.events_storage.list_events(author_username=params.author_username):
            occurrences.add_event(
                event=event,
                start_date=params.start_date,
                end_date=params.end_date,
                start_boundary=start_boundary,
                end_boundary=end_boundary,
                account_zone=account_zone,
            )
        months = tuple(range(1, 13))
        sources = CalendarSources.from_details(
            date_details=await self.dates_storage.list_details_for_months(
                months=months,
                author_username=params.author_username,
            ),
            birthday_details=await self.people_storage.list_birthday_details_for_months(
                months=months,
                author_username=params.author_username,
            ),
        )
        if not sources.is_empty:
            links = await self.dates_storage.list_person_links(
                date_ids=sources.date_ids,
                author_username=params.author_username,
            )
            date_items = await self.item_storage.get_items_by_ids(
                item_ids=sources.date_ids,
                author_username=params.author_username,
                kind=KnowledgeItemKind.DATE,
            )
            people = await self.item_storage.get_items_by_ids(
                item_ids=sources.person_ids(links=links),
                author_username=params.author_username,
                kind=KnowledgeItemKind.PERSON,
            )
            names = {item.id: item.display_name for item in [*date_items, *people]}
            related: dict[str, list[CalendarRelatedPerson]] = {
                date_id: [] for date_id in sources.date_ids
            }
            for link in links:
                related[link.date_id].append(
                    CalendarRelatedPerson(id=link.person_id, display_name=names[link.person_id]),
                )
            for persons in related.values():
                persons.sort(key=lambda person: (person.display_name.casefold(), person.id))
            for details in sources.date_details:
                occurrences.add_annual(
                    source_id=details.item_id,
                    kind=CalendarEntryKind.MEMORABLE_DATE,
                    display_name=names[details.item_id],
                    annual_date=CalendarAnnualDate(
                        day=details.date.day,
                        month=details.date.month,
                        year=details.date.year,
                    ),
                    related_people=related[details.item_id],
                    start_date=params.start_date,
                    end_date=params.end_date,
                )
            for source in sources.birthdays:
                occurrences.add_annual(
                    source_id=source.item_id,
                    kind=CalendarEntryKind.BIRTHDAY,
                    display_name=names[source.item_id],
                    annual_date=source.annual_date,
                    related_people=[],
                    start_date=params.start_date,
                    end_date=params.end_date,
                )
        occurrences.entries.sort(key=lambda entry: entry.sort_key(zone=account_zone))
        occurrences.unplaced_annual_entries.sort(
            key=lambda entry: (
                entry.annual_date.month,
                entry.annual_date.day,
                entry.display_name.casefold(),
                entry.source_id,
            ),
        )
        return occurrences
