from dataclasses import dataclass

from core.events.schemas import Event, EventDraft
from core.events.storages import EventsStorage


@dataclass(frozen=True, slots=True, kw_only=True)
class EventsUseCase:
    storage: EventsStorage

    async def list_events(self, *, author_username: str) -> list[Event]:
        return await self.storage.list_events(author_username=author_username)

    async def get_event(self, *, event_id: str, author_username: str) -> Event:
        return await self.storage.get_event(event_id=event_id, author_username=author_username)

    async def create_event(self, *, draft: EventDraft, author_username: str) -> Event:
        return await self.storage.create_event(draft=draft, author_username=author_username)

    async def update_event(
        self,
        *,
        event_id: str,
        draft: EventDraft,
        author_username: str,
    ) -> Event:
        await self.storage.get_event(event_id=event_id, author_username=author_username)
        return await self.storage.update_event(
            event_id=event_id,
            draft=draft,
            author_username=author_username,
        )

    async def delete_event(self, *, event_id: str, author_username: str) -> None:
        await self.storage.get_event(event_id=event_id, author_username=author_username)
        await self.storage.delete_event(event_id=event_id, author_username=author_username)
