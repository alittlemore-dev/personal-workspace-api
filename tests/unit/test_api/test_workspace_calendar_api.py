from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from httpx import codes

from core.account_time_zone.clients import AccountTimeZoneUnavailableError
from core.calendar.occurrences import CalendarOccurrence, CalendarOccurrences
from core.events.enums import EventFrequency
from core.events.schemas import Event, EventRecurrence
from core.important_info.schemas import ImportantInfo
from tests.test_cases import ApiTestCase
from tests.unit.conftest import TEST_USERNAME


class TestWorkspaceCalendarApi(ApiTestCase):
    @pytest_asyncio.fixture(autouse=True)
    async def setup(self) -> None:
        self.account_time_zone_reader = await self.container.get_account_time_zone_reader()
        self.info_use_case = await self.container.get_important_info_use_case()
        self.events_use_case = await self.container.get_events_use_case()
        self.occurrences_use_case = await self.container.get_calendar_occurrences_use_case()

    def test_important_info_crud_and_order_map_current_author(self) -> None:
        item = ImportantInfo(id="1" * 32, text="Keep this", position=0)
        self.info_use_case.list_items.return_value = [item]
        self.info_use_case.create_item.return_value = item
        self.info_use_case.update_item.return_value = item
        self.info_use_case.set_order.return_value = [item]

        assert self.api.get_important_info().json() == {
            "items": [{"id": item.id, "text": item.text, "position": 0}],
        }
        self.info_use_case.list_items.assert_awaited_once_with(author_username=TEST_USERNAME)
        assert (
            self.api.post_important_info(data={"text": " Keep this "}).status_code == codes.CREATED
        )
        self.info_use_case.create_item.assert_awaited_once_with(
            text="Keep this",
            author_username=TEST_USERNAME,
        )
        assert (
            self.api.put_important_info(item_id=item.id, data={"text": "Keep this"}).status_code
            == codes.OK
        )
        self.info_use_case.update_item.assert_awaited_once_with(
            item_id=item.id,
            text="Keep this",
            author_username=TEST_USERNAME,
        )
        assert self.api.put_important_info_order(data={"ids": [item.id]}).json() == {
            "items": [{"id": item.id, "text": item.text, "position": 0}],
        }
        self.info_use_case.set_order.assert_awaited_once_with(
            ids=[item.id],
            author_username=TEST_USERNAME,
        )
        assert self.api.delete_important_info(item_id=item.id).status_code == codes.NO_CONTENT
        self.info_use_case.delete_item.assert_awaited_once_with(
            item_id=item.id,
            author_username=TEST_USERNAME,
        )

    def test_important_info_accepts_multiple_empty_items_and_empty_updates(self) -> None:
        empty = ImportantInfo(id="1" * 32, text="", position=0)
        self.info_use_case.create_item.return_value = empty
        self.info_use_case.update_item.return_value = empty

        for _ in range(2):
            assert self.api.post_important_info(data={"text": ""}).status_code == codes.CREATED
        assert self.info_use_case.create_item.await_count == 2
        assert all(
            call.kwargs["text"] == "" for call in self.info_use_case.create_item.await_args_list
        )
        assert (
            self.api.put_important_info(item_id=empty.id, data={"text": " "}).status_code
            == codes.OK
        )
        self.info_use_case.update_item.assert_awaited_once_with(
            item_id=empty.id,
            text="",
            author_username=TEST_USERNAME,
        )

    @pytest.mark.parametrize("text", ["line one\nline two", "x" * 256])
    def test_important_info_rejects_invalid_text(self, text: str) -> None:
        response = self.api.post_important_info(data={"text": text})
        assert response.status_code == codes.BAD_REQUEST
        self.info_use_case.create_item.assert_not_called()

    def test_event_crud_serializes_utc_and_requires_explicit_fields(self) -> None:
        self.account_time_zone_reader.get_time_zone.return_value = ZoneInfo("Europe/Berlin")
        event = Event(
            id="2" * 32,
            title="Meeting",
            description="",
            anchor_time_zone=ZoneInfo("Europe/Berlin"),
            all_day=False,
            start=datetime(2026, 5, 1, 10, tzinfo=UTC),
            end=datetime(2026, 5, 1, 11, tzinfo=UTC),
            recurrence=EventRecurrence(frequency=EventFrequency.WEEKLY, until_date=None),
        )
        self.events_use_case.list_events.return_value = [event]
        self.events_use_case.get_event.return_value = event
        self.events_use_case.create_event.return_value = event
        self.events_use_case.update_event.return_value = event
        expected = {
            "id": event.id,
            "title": "Meeting",
            "description": "",
            "allDay": False,
            "start": "2026-05-01T10:00:00Z",
            "end": "2026-05-01T11:00:00Z",
            "recurrence": {"frequency": "weekly", "untilDate": None},
        }
        payload = {key: value for key, value in expected.items() if key != "id"}

        assert self.api.get_events().json() == {"events": [expected]}
        self.events_use_case.list_events.assert_awaited_once_with(author_username=TEST_USERNAME)
        assert self.api.post_event(data=payload).json() == expected
        self.events_use_case.create_event.assert_awaited_once()
        assert self.events_use_case.create_event.call_args.kwargs[
            "draft"
        ].anchor_time_zone == ZoneInfo("Europe/Berlin")
        assert self.api.get_event(event_id=event.id).json() == expected
        self.events_use_case.get_event.assert_awaited_once_with(
            event_id=event.id,
            author_username=TEST_USERNAME,
        )
        assert self.api.put_event(event_id=event.id, data=payload).json() == expected
        self.events_use_case.update_event.assert_awaited_once()
        assert self.api.delete_event(event_id=event.id).status_code == codes.NO_CONTENT
        self.events_use_case.delete_event.assert_awaited_once_with(
            event_id=event.id,
            author_username=TEST_USERNAME,
        )

    def test_event_create_and_update_accept_omitted_description_as_empty(self) -> None:
        event = Event(
            id="2" * 32,
            title="Meeting",
            description="",
            anchor_time_zone=ZoneInfo("UTC"),
            all_day=True,
            start=date(2026, 5, 1),
            end=date(2026, 5, 2),
            recurrence=EventRecurrence(frequency=EventFrequency.NONE, until_date=None),
        )
        self.events_use_case.create_event.return_value = event
        self.events_use_case.update_event.return_value = event
        payload = {
            "title": "Meeting",
            "allDay": True,
            "start": "2026-05-01",
            "end": "2026-05-02",
            "recurrence": {"frequency": "none", "untilDate": None},
        }

        created = self.api.post_event(data=payload)
        updated = self.api.put_event(event_id=event.id, data=payload)

        assert created.status_code == codes.CREATED
        assert updated.status_code == codes.OK
        assert created.json()["description"] == ""
        assert updated.json()["description"] == ""
        assert self.events_use_case.create_event.call_args.kwargs["draft"].description == ""
        assert self.events_use_case.update_event.call_args.kwargs["draft"].description == ""

    def test_event_read_uses_current_account_zone_for_recurring_first_occurrence(self) -> None:
        recurring = Event(
            id="3" * 32,
            title="Daily meeting",
            description="",
            anchor_time_zone=ZoneInfo("Europe/Berlin"),
            all_day=False,
            start=datetime(2026, 1, 1, 8, tzinfo=UTC),
            end=datetime(2026, 1, 1, 9, tzinfo=UTC),
            recurrence=EventRecurrence(frequency=EventFrequency.DAILY, until_date=None),
        )
        self.account_time_zone_reader.get_time_zone.return_value = ZoneInfo("Asia/Yerevan")
        self.events_use_case.get_event.return_value = recurring

        response = self.api.get_event(event_id=recurring.id)

        assert response.status_code == codes.OK
        assert response.json()["start"] == "2026-01-01T05:00:00Z"
        assert response.json()["end"] == "2026-01-01T06:00:00Z"
        assert "timeZone" not in response.json()

    def test_events_fail_closed_when_account_zone_is_unavailable(self) -> None:
        self.account_time_zone_reader.get_time_zone.side_effect = AccountTimeZoneUnavailableError()

        response = self.api.get_events()

        assert response.status_code == codes.SERVICE_UNAVAILABLE
        self.events_use_case.list_events.assert_not_awaited()

    @pytest.mark.parametrize(
        "payload_change",
        [
            {"start": "2026-05-01T12:00:00+02:00"},
            {"end": "2026-05-01T09:00:00Z"},
            {"recurrence": {"frequency": "none", "untilDate": "2026-05-02"}},
        ],
    )
    def test_event_rejects_invalid_time_contract(self, payload_change: dict[str, object]) -> None:
        payload: dict[str, object] = {
            "title": "Meeting",
            "description": "",
            "allDay": False,
            "start": "2026-05-01T10:00:00Z",
            "end": "2026-05-01T11:00:00Z",
            "recurrence": {"frequency": "none", "untilDate": None},
        }
        payload.update(payload_change)
        assert self.api.post_event(data=payload).status_code == codes.BAD_REQUEST
        self.events_use_case.create_event.assert_not_called()

    def test_occurrence_query_maps_range_and_rejects_invalid_range(self) -> None:
        occurrence = CalendarOccurrence(
            id="event:2026-05-01",
            source_id="event",
            kind="event",
            display_name="Meeting",
            all_day=True,
            start=date(2026, 5, 1),
            end=date(2026, 5, 2),
            annual_date=None,
            related_people=[],
        )
        self.occurrences_use_case.get_occurrences.return_value = CalendarOccurrences(
            entries=[occurrence],
            unplaced_annual_entries=[],
        )
        response = self.api.get_calendar_occurrences(
            start_date="2026-05-01",
            end_date="2026-05-31",
        )
        assert response.status_code == codes.OK
        assert response.json() == {
            "entries": [
                {
                    "id": occurrence.id,
                    "sourceId": "event",
                    "kind": "event",
                    "displayName": "Meeting",
                    "allDay": True,
                    "start": "2026-05-01",
                    "end": "2026-05-02",
                    "annualDate": None,
                    "relatedPeople": [],
                },
            ],
            "unplacedAnnualEntries": [],
        }
        self.occurrences_use_case.get_occurrences.assert_awaited_once_with(
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 31),
            author_username=TEST_USERNAME,
        )
        for start, end in [
            ("2026-05-01", "2026-05-01"),
            ("2026-05-01", "2027-07-01"),
        ]:
            invalid = self.api.get_calendar_occurrences(
                start_date=start,
                end_date=end,
            )
            assert invalid.status_code == codes.BAD_REQUEST
