from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.events.exceptions import EventNotFoundError
from core.events.schemas import Event, EventDraft
from core.events.storages import EventsStorage
from infra.postgresql.models.events import EventModel


@dataclass(kw_only=True)
class EventsDatabaseStorage(EventsStorage):
    session: AsyncSession

    async def list_events(self, *, author_username: str) -> list[Event]:
        query = (
            select(EventModel)
            .where(EventModel.author_username == author_username)
            .order_by(EventModel.start_date, EventModel.start_at, EventModel.id)
        )
        return [model.to_domain_schema() for model in await self.session.scalars(query)]

    async def get_event(self, *, event_id: str, author_username: str) -> Event:
        model = await self.session.scalar(
            select(EventModel).where(
                EventModel.id == event_id,
                EventModel.author_username == author_username,
            ),
        )
        if model is None:
            raise EventNotFoundError
        return model.to_domain_schema()

    async def create_event(self, *, draft: EventDraft, author_username: str) -> Event:
        model = EventModel.from_draft(draft=draft, author_username=author_username)
        self.session.add(model)
        await self.session.flush()
        return model.to_domain_schema()

    async def update_event(
        self,
        *,
        event_id: str,
        draft: EventDraft,
        author_username: str,
    ) -> Event:
        model = await self.session.scalar(
            select(EventModel).where(
                EventModel.id == event_id,
                EventModel.author_username == author_username,
            ),
        )
        if model is None:
            raise EventNotFoundError
        model.update_from_draft(draft=draft)
        await self.session.flush()
        return model.to_domain_schema()

    async def delete_event(self, *, event_id: str, author_username: str) -> None:
        deleted_id = await self.session.scalar(
            delete(EventModel)
            .where(
                EventModel.id == event_id,
                EventModel.author_username == author_username,
            )
            .returning(EventModel.id),
        )
        if deleted_id is None:
            raise EventNotFoundError
