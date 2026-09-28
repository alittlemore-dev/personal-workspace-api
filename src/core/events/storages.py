from abc import ABC, abstractmethod

from core.events.schemas import Event, EventDraft


class EventsStorage(ABC):
    @abstractmethod
    async def list_events(self, *, author_username: str) -> list[Event]:
        raise NotImplementedError

    @abstractmethod
    async def get_event(self, *, event_id: str, author_username: str) -> Event:
        raise NotImplementedError

    @abstractmethod
    async def create_event(self, *, draft: EventDraft, author_username: str) -> Event:
        raise NotImplementedError

    @abstractmethod
    async def update_event(
        self,
        *,
        event_id: str,
        draft: EventDraft,
        author_username: str,
    ) -> Event:
        raise NotImplementedError

    @abstractmethod
    async def delete_event(self, *, event_id: str, author_username: str) -> None:
        raise NotImplementedError
