from dataclasses import dataclass
from datetime import date

from core.calendar.enums import CalendarWindow
from core.calendar.schemas import Calendar, CalendarSources, CalendarWindowSelection
from core.knowledge.dates.storages import KnowledgeDatesStorage
from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.items.storages import KnowledgeItemsStorage
from core.knowledge.people.storages import PeopleStorage


@dataclass(kw_only=True, slots=True, frozen=True)
class CalendarUseCase:
    item_storage: KnowledgeItemsStorage
    dates_storage: KnowledgeDatesStorage
    people_storage: PeopleStorage

    async def get_calendar(
        self,
        *,
        reference_date: date,
        window: CalendarWindow,
        author_username: str,
    ) -> Calendar:
        selection = CalendarWindowSelection.from_reference_date(
            reference_date=reference_date,
            window=window,
        )
        sources = CalendarSources.from_details(
            date_details=await self.dates_storage.list_details_for_months(
                months=selection.months,
                author_username=author_username,
            ),
            birthday_details=await self.people_storage.list_birthday_details_for_months(
                months=selection.months,
                author_username=author_username,
            ),
        )
        if sources.is_empty:
            return Calendar.empty(selection=selection)
        links = await self.dates_storage.list_person_links(
            date_ids=sources.date_ids,
            author_username=author_username,
        )
        date_items = await self.item_storage.get_items_by_ids(
            item_ids=sources.date_ids,
            author_username=author_username,
            kind=KnowledgeItemKind.DATE,
        )
        people = await self.item_storage.get_items_by_ids(
            item_ids=sources.person_ids(links=links),
            author_username=author_username,
            kind=KnowledgeItemKind.PERSON,
        )
        return Calendar.from_sources(
            selection=selection,
            sources=sources,
            links=links,
            date_items=date_items,
            people=people,
        )
