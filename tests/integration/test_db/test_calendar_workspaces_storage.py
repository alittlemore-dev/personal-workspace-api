from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from core.events.enums import EventFrequency
from core.events.exceptions import EventNotFoundError
from core.events.schemas import EventDraft, EventRecurrence
from core.important_info.exceptions import ImportantInfoNotFoundError
from core.important_info.schemas import (
    CreateImportantInfoParams,
    ImportantInfoTargetParams,
    SetImportantInfoOrderParams,
    UpdateImportantInfoParams,
)
from core.important_info.use_cases import ImportantInfoUseCase
from infra.postgresql.storages.events import EventsDatabaseStorage
from infra.postgresql.storages.important_info import ImportantInfoDatabaseStorage
from tests.test_cases import StorageTestCase


class TestCalendarWorkspacesStorage(StorageTestCase):
    async def test_important_info_stores_multiple_blank_items(self) -> None:
        use_case = ImportantInfoUseCase(
            storage=ImportantInfoDatabaseStorage(session=self.db_session),
        )
        first = await use_case.create_item(
            params=CreateImportantInfoParams(
                text="",
                author_username="owner",
            ),
        )
        second = await use_case.create_item(
            params=CreateImportantInfoParams(
                text="",
                author_username="owner",
            ),
        )

        assert first.id != second.id
        assert [
            (item.text, item.position)
            for item in await use_case.list_items(author_username="owner")
        ] == [
            ("", 0),
            ("", 1),
        ]

    async def test_important_info_is_author_scoped_and_reorders_only_own_items(self) -> None:
        storage = ImportantInfoDatabaseStorage(session=self.db_session)
        use_case = ImportantInfoUseCase(storage=storage)
        first = await use_case.create_item(
            params=CreateImportantInfoParams(
                text="First",
                author_username="owner",
            ),
        )
        second = await use_case.create_item(
            params=CreateImportantInfoParams(
                text="Second",
                author_username="owner",
            ),
        )
        foreign = await use_case.create_item(
            params=CreateImportantInfoParams(
                text="Foreign",
                author_username="another",
            ),
        )

        assert [item.text for item in await use_case.list_items(author_username="owner")] == [
            "First",
            "Second",
        ]
        ordered = await use_case.set_order(
            params=SetImportantInfoOrderParams(
                ids=[second.id, first.id],
                author_username="owner",
            ),
        )
        assert [(item.id, item.position) for item in ordered] == [(second.id, 0), (first.id, 1)]
        assert [item.id for item in await use_case.list_items(author_username="another")] == [
            foreign.id,
        ]
        with pytest.raises(ImportantInfoNotFoundError):
            await use_case.update_item(
                params=UpdateImportantInfoParams(
                    item_id=foreign.id,
                    text="Stolen",
                    author_username="owner",
                ),
            )
        with pytest.raises(ImportantInfoNotFoundError):
            await use_case.delete_item(
                params=ImportantInfoTargetParams(
                    item_id=foreign.id,
                    author_username="owner",
                ),
            )
        assert (
            await storage.get_item(item_id=foreign.id, author_username="another")
        ).text == "Foreign"

    async def test_event_roundtrip_and_foreign_id_cannot_read_or_mutate(self) -> None:
        storage = EventsDatabaseStorage(session=self.db_session)
        draft = EventDraft(
            title="Meeting",
            description="Plan",
            anchor_time_zone=ZoneInfo("Europe/Berlin"),
            all_day=False,
            start=datetime(2026, 10, 24, 9, tzinfo=UTC),
            end=datetime(2026, 10, 24, 10, tzinfo=UTC),
            recurrence=EventRecurrence(
                frequency=EventFrequency.WEEKLY,
                until_date=date(2026, 12, 1),
            ),
        )
        created = await storage.create_event(draft=draft, author_username="owner")
        assert await storage.get_event(event_id=created.id, author_username="owner") == created
        assert [item.id for item in await storage.list_events(author_username="owner")] == [
            created.id,
        ]
        assert await storage.list_events(author_username="another") == []
        with pytest.raises(EventNotFoundError):
            await storage.get_event(event_id=created.id, author_username="another")
        with pytest.raises(EventNotFoundError):
            await storage.update_event(event_id=created.id, draft=draft, author_username="another")
        with pytest.raises(EventNotFoundError):
            await storage.delete_event(event_id=created.id, author_username="another")
        assert (
            await storage.get_event(event_id=created.id, author_username="owner")
        ).title == "Meeting"
        await storage.delete_event(event_id=created.id, author_username="owner")
        with pytest.raises(EventNotFoundError):
            await storage.get_event(event_id=created.id, author_username="owner")
