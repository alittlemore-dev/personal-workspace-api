from dataclasses import dataclass

from core.events.schemas import (
    CreateEventParams,
    Event,
    EventTargetParams,
    UpdateEventParams,
)
from core.events.storages import EventsStorage


@dataclass(frozen=True, slots=True, kw_only=True)
class EventsUseCase:
    storage: EventsStorage

    async def list_events(self, *, author_username: str) -> list[Event]:
        return await self.storage.list_events(author_username=author_username)

    async def get_event(self, *, params: EventTargetParams) -> Event:
        return await self.storage.get_event(
            event_id=params.event_id,
            author_username=params.author_username,
        )

    async def create_event(self, *, params: CreateEventParams) -> Event:
        return await self.storage.create_event(
            draft=params.draft,
            author_username=params.author_username,
        )

    async def update_event(self, *, params: UpdateEventParams) -> Event:
        await self.storage.get_event(
            event_id=params.event_id,
            author_username=params.author_username,
        )
        return await self.storage.update_event(
            event_id=params.event_id,
            draft=params.draft,
            author_username=params.author_username,
        )

    async def delete_event(self, *, params: EventTargetParams) -> None:
        await self.storage.get_event(
            event_id=params.event_id,
            author_username=params.author_username,
        )
        await self.storage.delete_event(
            event_id=params.event_id,
            author_username=params.author_username,
        )
