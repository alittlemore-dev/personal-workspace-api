from datetime import UTC, date, datetime
from typing import cast
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest

from core.account_time_zone.clients import AccountTimeZoneReader
from core.calendar.occurrences import CalendarOccurrencesUseCase
from core.events.enums import EventFrequency
from core.events.schemas import Event, EventDraft, EventRecurrence
from core.knowledge.dates.schemas import KnowledgeDateDetails, KnowledgeDateValue
from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.items.schemas import KnowledgeItem
from core.knowledge.people.schemas import PersonBirthday, PersonDetails


def event(  # noqa: PLR0913
    *,
    start: date | datetime,
    end: date | datetime,
    frequency: EventFrequency,
    until_date: date | None,
    all_day: bool,
    time_zone: str,
) -> Event:
    draft = EventDraft(
        title="Meeting",
        description="",
        anchor_time_zone=ZoneInfo(time_zone),
        all_day=all_day,
        start=start,
        end=end,
        recurrence=EventRecurrence(frequency=frequency, until_date=until_date),
    )
    return Event.from_draft(event_id="a" * 32, draft=draft)


def use_case(*, events: list[Event]) -> CalendarOccurrencesUseCase:
    item_storage = Mock()
    date_storage = Mock()
    people_storage = Mock()
    events_storage = Mock()
    events_storage.list_events = AsyncMock(return_value=events)
    account_time_zone_reader = AsyncMock(spec=AccountTimeZoneReader)
    account_time_zone_reader.get_time_zone.return_value = (
        events[0].anchor_time_zone if events else ZoneInfo("UTC")
    )
    date_storage.list_details_for_months = AsyncMock(return_value=[])
    people_storage.list_birthday_details_for_months = AsyncMock(return_value=[])
    return CalendarOccurrencesUseCase(
        item_storage=item_storage,
        dates_storage=date_storage,
        people_storage=people_storage,
        events_storage=events_storage,
        account_time_zone_reader=account_time_zone_reader,
    )


@pytest.mark.asyncio
async def test_monthly_recurrence_clamps_from_original_day() -> None:
    calendar = use_case(
        events=[
            event(
                start=date(2026, 1, 31),
                end=date(2026, 2, 2),
                frequency=EventFrequency.MONTHLY,
                until_date=date(2026, 3, 31),
                all_day=True,
                time_zone="UTC",
            ),
        ],
    )

    result = await calendar.get_occurrences(
        start_date=date(2026, 2, 1),
        end_date=date(2026, 4, 1),
        author_username="owner",
    )

    assert [(entry.start, entry.end) for entry in result.entries] == [
        (date(2026, 1, 31), date(2026, 2, 2)),
        (date(2026, 2, 28), date(2026, 3, 2)),
        (date(2026, 3, 31), date(2026, 4, 2)),
    ]


@pytest.mark.asyncio
async def test_yearly_february_29_event_clamps_to_february_28() -> None:
    calendar = use_case(
        events=[
            event(
                start=date(2024, 2, 29),
                end=date(2024, 3, 1),
                frequency=EventFrequency.YEARLY,
                until_date=date(2028, 2, 29),
                all_day=True,
                time_zone="UTC",
            ),
        ],
    )
    result = await calendar.get_occurrences(
        start_date=date(2025, 2, 1),
        end_date=date(2025, 3, 2),
        author_username="owner",
    )
    assert [(entry.start, entry.end) for entry in result.entries] == [
        (date(2025, 2, 28), date(2025, 3, 1)),
    ]


@pytest.mark.asyncio
async def test_daily_timed_event_keeps_wall_time_through_dst() -> None:
    calendar = use_case(
        events=[
            event(
                start=datetime(2026, 3, 28, 9, tzinfo=UTC),
                end=datetime(2026, 3, 28, 10, tzinfo=UTC),
                frequency=EventFrequency.DAILY,
                until_date=date(2026, 3, 30),
                all_day=False,
                time_zone="Europe/Berlin",
            ),
        ],
    )
    result = await calendar.get_occurrences(
        start_date=date(2026, 3, 28),
        end_date=date(2026, 3, 31),
        author_username="owner",
    )
    assert [entry.start for entry in result.entries] == [
        datetime(2026, 3, 28, 9, tzinfo=UTC),
        datetime(2026, 3, 29, 8, tzinfo=UTC),
        datetime(2026, 3, 30, 8, tzinfo=UTC),
    ]
    assert [entry.end for entry in result.entries] == [
        datetime(2026, 3, 28, 10, tzinfo=UTC),
        datetime(2026, 3, 29, 9, tzinfo=UTC),
        datetime(2026, 3, 30, 9, tzinfo=UTC),
    ]


def test_ambiguous_fall_time_keeps_original_start_and_end_clocks() -> None:
    fall_event = event(
        start=datetime(2026, 10, 24, 0, 30, tzinfo=UTC),
        end=datetime(2026, 10, 24, 1, 30, tzinfo=UTC),
        frequency=EventFrequency.DAILY,
        until_date=None,
        all_day=False,
        time_zone="Europe/Berlin",
    )
    assert fall_event.occurrence_at(index=1, time_zone=ZoneInfo("Europe/Berlin")) == (
        datetime(2026, 10, 25, 0, 30, tzinfo=UTC),
        datetime(2026, 10, 25, 2, 30, tzinfo=UTC),
    )

    multiday_event = event(
        start=datetime(2026, 3, 27, 21, tzinfo=UTC),
        end=datetime(2026, 3, 29, 7, tzinfo=UTC),
        frequency=EventFrequency.WEEKLY,
        until_date=None,
        all_day=False,
        time_zone="Europe/Berlin",
    )
    assert multiday_event.occurrence_at(index=1, time_zone=ZoneInfo("Europe/Berlin")) == (
        datetime(2026, 4, 3, 20, tzinfo=UTC),
        datetime(2026, 4, 5, 7, tzinfo=UTC),
    )


def test_timed_month_end_multiday_keeps_original_wall_day_span() -> None:
    value = event(
        start=datetime(2026, 1, 30, 22, tzinfo=UTC),
        end=datetime(2026, 2, 1, 9, tzinfo=UTC),
        frequency=EventFrequency.MONTHLY,
        until_date=None,
        all_day=False,
        time_zone="UTC",
    )
    assert value.occurrence_at(index=1, time_zone=ZoneInfo("UTC")) == (
        datetime(2026, 2, 28, 22, tzinfo=UTC),
        datetime(2026, 3, 2, 9, tzinfo=UTC),
    )
    assert value.occurrence_at(index=2, time_zone=ZoneInfo("UTC")) == (
        datetime(2026, 3, 30, 22, tzinfo=UTC),
        datetime(2026, 4, 1, 9, tzinfo=UTC),
    )


def test_first_timed_occurrence_preserves_fall_fold_one_instant() -> None:
    value = event(
        start=datetime(2026, 11, 1, 6, 30, tzinfo=UTC),
        end=datetime(2026, 11, 1, 7, 30, tzinfo=UTC),
        frequency=EventFrequency.DAILY,
        until_date=None,
        all_day=False,
        time_zone="America/New_York",
    )
    assert value.occurrence_at(index=0, time_zone=ZoneInfo("America/New_York")) == (
        value.start,
        value.end,
    )


def test_account_zone_retimes_existing_recurring_wall_clock_but_not_one_off() -> None:
    recurring = event(
        start=datetime(2026, 1, 1, 8, tzinfo=UTC),
        end=datetime(2026, 1, 1, 9, tzinfo=UTC),
        frequency=EventFrequency.DAILY,
        until_date=None,
        all_day=False,
        time_zone="Europe/Berlin",
    )
    assert recurring.occurrence_at(index=0, time_zone=ZoneInfo("Asia/Yerevan")) == (
        datetime(2026, 1, 1, 5, tzinfo=UTC),
        datetime(2026, 1, 1, 6, tzinfo=UTC),
    )
    assert recurring.occurrence_at(index=1, time_zone=ZoneInfo("Asia/Yerevan")) == (
        datetime(2026, 1, 2, 5, tzinfo=UTC),
        datetime(2026, 1, 2, 6, tzinfo=UTC),
    )
    one_off = event(
        start=recurring.start,
        end=recurring.end,
        frequency=EventFrequency.NONE,
        until_date=None,
        all_day=False,
        time_zone="Europe/Berlin",
    )
    assert one_off.occurrence_at(index=0, time_zone=ZoneInfo("Asia/Yerevan")) == (
        one_off.start,
        one_off.end,
    )


@pytest.mark.asyncio
async def test_calendar_view_zone_does_not_set_recurring_schedule_zone() -> None:
    calendar = use_case(
        events=[
            event(
                start=datetime(2026, 1, 1, 8, tzinfo=UTC),
                end=datetime(2026, 1, 1, 9, tzinfo=UTC),
                frequency=EventFrequency.DAILY,
                until_date=date(2026, 1, 2),
                all_day=False,
                time_zone="Europe/Berlin",
            ),
        ],
    )
    reader = cast("AsyncMock", calendar.account_time_zone_reader)
    reader.get_time_zone.return_value = ZoneInfo("Asia/Yerevan")

    result = await calendar.get_occurrences(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        author_username="owner",
    )

    assert [entry.start for entry in result.entries] == [
        datetime(2026, 1, 1, 5, tzinfo=UTC),
        datetime(2026, 1, 2, 5, tzinfo=UTC),
    ]


@pytest.mark.asyncio
async def test_calendar_range_uses_account_day_boundaries() -> None:
    calendar = use_case(
        events=[
            event(
                start=datetime(2026, 1, 1, 20, 30, tzinfo=UTC),
                end=datetime(2026, 1, 1, 21, 30, tzinfo=UTC),
                frequency=EventFrequency.NONE,
                until_date=None,
                all_day=False,
                time_zone="UTC",
            ),
        ],
    )
    reader = cast("AsyncMock", calendar.account_time_zone_reader)
    reader.get_time_zone.return_value = ZoneInfo("Asia/Yerevan")

    result = await calendar.get_occurrences(
        start_date=date(2026, 1, 2),
        end_date=date(2026, 1, 3),
        author_username="owner",
    )

    assert [entry.start for entry in result.entries] == [
        datetime(2026, 1, 1, 20, 30, tzinfo=UTC),
    ]


def test_later_ambiguous_start_reuses_original_fold() -> None:
    value = event(
        start=datetime(2026, 11, 1, 6, 30, tzinfo=UTC),
        end=datetime(2026, 11, 1, 7, 30, tzinfo=UTC),
        frequency=EventFrequency.WEEKLY,
        until_date=None,
        all_day=False,
        time_zone="America/New_York",
    )
    assert value.occurrence_at(index=53, time_zone=ZoneInfo("America/New_York")) == (
        datetime(2027, 11, 7, 6, 30, tzinfo=UTC),
        datetime(2027, 11, 7, 7, 30, tzinfo=UTC),
    )


def test_one_off_event_spanning_repeated_hour_keeps_original_utc_endpoints() -> None:
    value = event(
        start=datetime(2026, 11, 1, 5, 30, tzinfo=UTC),
        end=datetime(2026, 11, 1, 6, 45, tzinfo=UTC),
        frequency=EventFrequency.NONE,
        until_date=None,
        all_day=False,
        time_zone="America/New_York",
    )
    assert value.occurrence_at(index=0, time_zone=ZoneInfo("America/New_York")) == (
        value.start,
        value.end,
    )


@pytest.mark.asyncio
async def test_range_keeps_one_off_event_spanning_repeated_hour() -> None:
    value = event(
        start=datetime(2026, 11, 1, 5, 30, tzinfo=UTC),
        end=datetime(2026, 11, 1, 6, 45, tzinfo=UTC),
        frequency=EventFrequency.NONE,
        until_date=None,
        all_day=False,
        time_zone="America/New_York",
    )
    calendar = use_case(events=[value])
    result = await calendar.get_occurrences(
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 2),
        author_username="owner",
    )
    assert [(entry.start, entry.end) for entry in result.entries] == [
        (value.start, value.end),
    ]


def test_spring_gap_moves_forward_and_preserves_elapsed_duration() -> None:
    value = event(
        start=datetime(2026, 3, 7, 7, 30, tzinfo=UTC),
        end=datetime(2026, 3, 7, 8, 30, tzinfo=UTC),
        frequency=EventFrequency.DAILY,
        until_date=None,
        all_day=False,
        time_zone="America/New_York",
    )
    assert value.occurrence_at(index=1, time_zone=ZoneInfo("America/New_York")) == (
        datetime(2026, 3, 8, 7, 30, tzinfo=UTC),
        datetime(2026, 3, 8, 8, 30, tzinfo=UTC),
    )


def test_timed_monthly_recurrence_clamps_from_original_day_and_clock() -> None:
    value = event(
        start=datetime(2026, 1, 31, 9, tzinfo=UTC),
        end=datetime(2026, 1, 31, 10, 30, tzinfo=UTC),
        frequency=EventFrequency.MONTHLY,
        until_date=None,
        all_day=False,
        time_zone="UTC",
    )
    assert value.occurrence_at(index=1, time_zone=ZoneInfo("UTC")) == (
        datetime(2026, 2, 28, 9, tzinfo=UTC),
        datetime(2026, 2, 28, 10, 30, tzinfo=UTC),
    )
    assert value.occurrence_at(index=2, time_zone=ZoneInfo("UTC")) == (
        datetime(2026, 3, 31, 9, tzinfo=UTC),
        datetime(2026, 3, 31, 10, 30, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_timed_event_starting_before_range_is_included_when_it_overlaps() -> None:
    calendar = use_case(
        events=[
            event(
                start=datetime(2026, 5, 1, 23, tzinfo=UTC),
                end=datetime(2026, 5, 3, 1, tzinfo=UTC),
                frequency=EventFrequency.NONE,
                until_date=None,
                all_day=False,
                time_zone="UTC",
            ),
        ],
    )
    result = await calendar.get_occurrences(
        start_date=date(2026, 5, 2),
        end_date=date(2026, 5, 3),
        author_username="owner",
    )
    assert len(result.entries) == 1
    assert result.entries[0].start == datetime(2026, 5, 1, 23, tzinfo=UTC)


@pytest.mark.asyncio
async def test_legacy_february_29_annual_sources_remain_unplaced_in_nonleap_year() -> None:
    calendar = use_case(events=[])
    date_storage = cast("Mock", calendar.dates_storage)
    people_storage = cast("Mock", calendar.people_storage)
    item_storage = cast("Mock", calendar.item_storage)
    date_id = "1" * 32
    person_id = "2" * 32
    date_storage.list_details_for_months.return_value = [
        KnowledgeDateDetails(
            item_id=date_id,
            date=KnowledgeDateValue(day=29, month=2, year=None),
            notifications_enabled=True,
        ),
    ]
    people_storage.list_birthday_details_for_months.return_value = [
        PersonDetails(
            item_id=person_id,
            last_name="Doe",
            first_name="Jane",
            middle_name="",
            email="",
            phone="",
            telegram="",
            birthday=PersonBirthday(day=29, month=2, year=2000),
            notifications_enabled=True,
        ),
    ]
    date_storage.list_person_links = AsyncMock(return_value=[])

    def item(*, item_id: str, kind: KnowledgeItemKind, name: str) -> KnowledgeItem:
        return KnowledgeItem(
            id=item_id,
            kind=kind,
            author_username="owner",
            display_name=name,
            description="",
            tags=[],
            created_at=datetime(2025, 1, 1, tzinfo=UTC),
            updated_at=datetime(2025, 1, 1, tzinfo=UTC),
        )

    item_storage.get_items_by_ids = AsyncMock(
        side_effect=[
            [item(item_id=date_id, kind=KnowledgeItemKind.DATE, name="Anniversary")],
            [item(item_id=person_id, kind=KnowledgeItemKind.PERSON, name="Jane Doe")],
        ],
    )

    result = await calendar.get_occurrences(
        start_date=date(2025, 2, 1),
        end_date=date(2025, 3, 1),
        author_username="owner",
    )

    assert result.entries == []
    assert [(entry.source_id, entry.kind.value) for entry in result.unplaced_annual_entries] == [
        (date_id, "memorableDate"),
        (person_id, "birthday"),
    ]
