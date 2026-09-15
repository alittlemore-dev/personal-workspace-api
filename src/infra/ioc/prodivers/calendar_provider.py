from dishka import Provider, Scope, provide

from core.calendar.use_cases import CalendarUseCase
from core.knowledge.dates.storages import KnowledgeDatesStorage
from core.knowledge.items.storages import KnowledgeItemsStorage
from core.knowledge.people.storages import PeopleStorage


class CalendarProvider(Provider):
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
