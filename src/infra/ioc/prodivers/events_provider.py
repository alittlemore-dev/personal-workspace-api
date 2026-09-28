from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from core.events.storages import EventsStorage
from core.events.use_cases import EventsUseCase
from infra.postgresql.storages.events import EventsDatabaseStorage


class EventsProvider(Provider):
    @provide(scope=Scope.REQUEST)
    async def provide_events_storage(self, session: AsyncSession) -> EventsStorage:
        return EventsDatabaseStorage(session=session)

    @provide(scope=Scope.REQUEST)
    async def provide_events_use_case(self, storage: EventsStorage) -> EventsUseCase:
        return EventsUseCase(storage=storage)
