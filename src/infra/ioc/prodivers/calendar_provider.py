from dishka import Provider, Scope, provide

from core.account_time_zone.clients import AccountTimeZoneReader
from core.calendar.occurrences import CalendarOccurrencesUseCase
from core.calendar.use_cases import CalendarUseCase
from core.events.storages import EventsStorage
from core.knowledge.dates.storages import KnowledgeDatesStorage
from core.knowledge.items.storages import KnowledgeItemsStorage
from core.knowledge.people.storages import PeopleStorage


class CalendarProvider(Provider):
    @provide(scope=Scope.REQUEST)
    async def provide_calendar_occurrences_use_case(
        self,
        item_storage: KnowledgeItemsStorage,
        dates_storage: KnowledgeDatesStorage,
        people_storage: PeopleStorage,
        events_storage: EventsStorage,
        account_time_zone_reader: AccountTimeZoneReader,
    ) -> CalendarOccurrencesUseCase:
        return CalendarOccurrencesUseCase(
            item_storage=item_storage,
            dates_storage=dates_storage,
            people_storage=people_storage,
            events_storage=events_storage,
            account_time_zone_reader=account_time_zone_reader,
        )

    @provide(scope=Scope.REQUEST)
    async def provide_calendar_use_case(
        self,
        item_storage: KnowledgeItemsStorage,
        dates_storage: KnowledgeDatesStorage,
        people_storage: PeopleStorage,
    ) -> CalendarUseCase:
        return CalendarUseCase(
            item_storage=item_storage,
            dates_storage=dates_storage,
            people_storage=people_storage,
        )
