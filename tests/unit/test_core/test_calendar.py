from datetime import UTC, date, datetime
from unittest.mock import Mock, call

import pytest

from core.calendar.enums import CalendarEntryKind, CalendarEntryPeriod, CalendarWindow
from core.calendar.schemas import (
    Calendar,
    CalendarSources,
    CalendarSummary,
    CalendarWindowSelection,
)
from core.calendar.use_cases import CalendarUseCase
from core.knowledge.dates.schemas import (
    KnowledgeDateDetails,
    KnowledgeDatePersonLink,
    KnowledgeDateValue,
)
from core.knowledge.dates.storages import KnowledgeDatesStorage
from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.items.schemas import KnowledgeItem
from core.knowledge.items.storages import KnowledgeItemsStorage
from core.knowledge.people.schemas import PersonBirthday, PersonDetails
from core.knowledge.people.storages import PeopleStorage
from tests.test_cases import TestCase

CURRENT_DATETIME = datetime(2026, 7, 31, 12, tzinfo=UTC)


def knowledge_item(
    *,
    item_id: str,
    kind: KnowledgeItemKind,
    display_name: str,
) -> KnowledgeItem:
    return KnowledgeItem(
        id=item_id,
        kind=kind,
        author_username="owner",
        display_name=display_name,
        description="",
        tags=[],
        created_at=CURRENT_DATETIME,
        updated_at=CURRENT_DATETIME,
    )


class TestCalendarSchema(TestCase):
    def test_composes_summarizes_and_sorts_dates_birthdays_and_related_people(self) -> None:
        current_date_id = self.factory.core.hex_id(1)
        next_date_id = self.factory.core.hex_id(2)
        current_birthday_id = self.factory.core.hex_id(3)
        next_birthday_id = self.factory.core.hex_id(4)
        related_person_id = self.factory.core.hex_id(5)
        selection = CalendarWindowSelection.from_reference_date(
            reference_date=date(2026, 7, 31),
            window=CalendarWindow.CURRENT_AND_NEXT_MONTHS,
        )
        sources = CalendarSources.from_details(
            date_details=[
                KnowledgeDateDetails(
                    item_id=next_date_id,
                    date=KnowledgeDateValue(day=2, month=8, year=None),
                ),
                KnowledgeDateDetails(
                    item_id=current_date_id,
                    date=KnowledgeDateValue(day=20, month=7, year=2020),
                ),
            ],
            birthday_details=[
                PersonDetails(
                    item_id=next_birthday_id,
                    last_name="Следующий",
                    first_name="День рождения",
                    middle_name="",
                    email="",
                    phone="",
                    telegram="",
                    birthday=PersonBirthday(day=2, month=8, year=2000),
                ),
                PersonDetails(
                    item_id=current_birthday_id,
                    last_name="Текущий",
                    first_name="День рождения",
                    middle_name="",
                    email="",
                    phone="",
                    telegram="",
                    birthday=PersonBirthday(day=20, month=7, year=None),
                ),
            ],
        )

        calendar = Calendar.from_sources(
            selection=selection,
            sources=sources,
            links=[
                KnowledgeDatePersonLink(
                    date_id=current_date_id,
                    person_id=related_person_id,
                ),
            ],
            date_items=[
                knowledge_item(
                    item_id=current_date_id,
                    kind=KnowledgeItemKind.DATE,
                    display_name="Текущая дата",
                ),
                knowledge_item(
                    item_id=next_date_id,
                    kind=KnowledgeItemKind.DATE,
                    display_name="Следующая дата",
                ),
            ],
            people=[
                knowledge_item(
                    item_id=current_birthday_id,
                    kind=KnowledgeItemKind.PERSON,
                    display_name="Текущий день рождения",
                ),
                knowledge_item(
                    item_id=next_birthday_id,
                    kind=KnowledgeItemKind.PERSON,
                    display_name="Следующий день рождения",
                ),
                knowledge_item(
                    item_id=related_person_id,
                    kind=KnowledgeItemKind.PERSON,
                    display_name="Кого поздравить",
                ),
            ],
        )

        assert [entry.id for entry in calendar.entries] == [
            current_date_id,
            current_birthday_id,
            next_date_id,
            next_birthday_id,
        ]
        assert [entry.kind for entry in calendar.entries] == [
            CalendarEntryKind.MEMORABLE_DATE,
            CalendarEntryKind.BIRTHDAY,
            CalendarEntryKind.MEMORABLE_DATE,
            CalendarEntryKind.BIRTHDAY,
        ]
        assert [entry.period for entry in calendar.entries] == [
            CalendarEntryPeriod.CURRENT_MONTH,
            CalendarEntryPeriod.CURRENT_MONTH,
            CalendarEntryPeriod.NEXT_MONTH,
            CalendarEntryPeriod.NEXT_MONTH,
        ]
        assert [entry.occurrence_year for entry in calendar.entries] == [2026] * 4
        assert calendar.entries[0].related_people[0].display_name == "Кого поздравить"
        assert calendar.entries[1].related_people == []
        assert calendar.summary.memorable_date_count == 2
        assert calendar.summary.birthday_count == 2
        assert calendar.window == CalendarWindow.CURRENT_AND_NEXT_MONTHS

    def test_rolls_the_next_month_into_the_next_year(self) -> None:
        december_id = self.factory.core.hex_id(1)
        january_id = self.factory.core.hex_id(2)
        selection = CalendarWindowSelection.from_reference_date(
            reference_date=date(2026, 12, 15),
            window=CalendarWindow.CURRENT_AND_NEXT_MONTHS,
        )
        sources = CalendarSources.from_details(
            date_details=[
                KnowledgeDateDetails(
                    item_id=december_id,
                    date=KnowledgeDateValue(day=31, month=12, year=2020),
                ),
                KnowledgeDateDetails(
                    item_id=january_id,
                    date=KnowledgeDateValue(day=1, month=1, year=2020),
                ),
            ],
            birthday_details=[],
        )

        calendar = Calendar.from_sources(
            selection=selection,
            sources=sources,
            links=[],
            date_items=[
                knowledge_item(
                    item_id=december_id,
                    kind=KnowledgeItemKind.DATE,
                    display_name="Декабрь",
                ),
                knowledge_item(
                    item_id=january_id,
                    kind=KnowledgeItemKind.DATE,
                    display_name="Январь",
                ),
            ],
            people=[],
        )

        assert [entry.id for entry in calendar.entries] == [december_id, january_id]
        assert [entry.occurrence_year for entry in calendar.entries] == [2026, 2027]

    @pytest.mark.parametrize("reference_year", [2027, 2028])
    def test_keeps_february_29_in_the_february_month_window(self, reference_year: int) -> None:
        date_id = self.factory.core.hex_id(1)
        selection = CalendarWindowSelection.from_reference_date(
            reference_date=date(reference_year, 2, 1),
            window=CalendarWindow.MONTH,
        )
        sources = CalendarSources.from_details(
            date_details=[
                KnowledgeDateDetails(
                    item_id=date_id,
                    date=KnowledgeDateValue(day=29, month=2, year=None),
                ),
            ],
            birthday_details=[],
        )

        calendar = Calendar.from_sources(
            selection=selection,
            sources=sources,
            links=[],
            date_items=[
                knowledge_item(
                    item_id=date_id,
                    kind=KnowledgeItemKind.DATE,
                    display_name="29 февраля",
                ),
            ],
            people=[],
        )

        assert calendar.entries[0].annual_date.day == 29
        assert calendar.entries[0].occurrence_year == reference_year


class TestCalendarUseCase(TestCase):
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.item_storage = Mock(spec=KnowledgeItemsStorage)
        self.dates_storage = Mock(spec=KnowledgeDatesStorage)
        self.people_storage = Mock(spec=PeopleStorage)
        self.use_case = CalendarUseCase(
            item_storage=self.item_storage,
            dates_storage=self.dates_storage,
            people_storage=self.people_storage,
        )

    @pytest.mark.parametrize(
        ("window", "expected_months"),
        [
            (CalendarWindow.MONTH, (7,)),
            (CalendarWindow.CURRENT_AND_NEXT_MONTHS, (7, 8)),
        ],
    )
    async def test_reads_the_selected_months_for_the_author(
        self,
        window: CalendarWindow,
        expected_months: tuple[int, ...],
    ) -> None:
        self.dates_storage.list_details_for_months.return_value = []
        self.people_storage.list_birthday_details_for_months.return_value = []

        calendar = await self.use_case.get_calendar(
            reference_date=date(2026, 7, 31),
            window=window,
            author_username="owner",
        )

        assert calendar == Calendar.empty(
            selection=CalendarWindowSelection.from_reference_date(
                reference_date=date(2026, 7, 31),
                window=window,
            ),
        )
        self.dates_storage.list_details_for_months.assert_awaited_once_with(
            months=expected_months,
            author_username="owner",
        )
        self.people_storage.list_birthday_details_for_months.assert_awaited_once_with(
            months=expected_months,
            author_username="owner",
        )
        self.dates_storage.list_person_links.assert_not_called()
        self.item_storage.get_items_by_ids.assert_not_called()

    async def test_reads_related_items_only_for_the_author(self) -> None:
        date_id = self.factory.core.hex_id(1)
        birthday_id = self.factory.core.hex_id(2)
        related_person_id = self.factory.core.hex_id(3)
        self.dates_storage.list_details_for_months.return_value = [
            KnowledgeDateDetails(
                item_id=date_id,
                date=KnowledgeDateValue(day=20, month=7, year=2020),
            ),
        ]
        self.people_storage.list_birthday_details_for_months.return_value = [
            PersonDetails(
                item_id=birthday_id,
                last_name="Иванов",
                first_name="Иван",
                middle_name="",
                email="",
                phone="",
                telegram="",
                birthday=PersonBirthday(day=21, month=7, year=2000),
            ),
        ]
        self.dates_storage.list_person_links.return_value = [
            KnowledgeDatePersonLink(date_id=date_id, person_id=related_person_id),
        ]
        self.item_storage.get_items_by_ids.side_effect = [
            [
                knowledge_item(
                    item_id=date_id,
                    kind=KnowledgeItemKind.DATE,
                    display_name="Годовщина",
                ),
            ],
            [
                knowledge_item(
                    item_id=birthday_id,
                    kind=KnowledgeItemKind.PERSON,
                    display_name="Иван Иванов",
                ),
                knowledge_item(
                    item_id=related_person_id,
                    kind=KnowledgeItemKind.PERSON,
                    display_name="Анна",
                ),
            ],
        ]

        calendar = await self.use_case.get_calendar(
            reference_date=date(2026, 7, 31),
            window=CalendarWindow.MONTH,
            author_username="owner",
        )

        assert calendar.summary == CalendarSummary(
            memorable_date_count=1,
            birthday_count=1,
        )
        self.dates_storage.list_person_links.assert_awaited_once_with(
            date_ids={date_id},
            author_username="owner",
        )
        assert self.item_storage.get_items_by_ids.await_args_list == [
            call(
                item_ids={date_id},
                author_username="owner",
                kind=KnowledgeItemKind.DATE,
            ),
            call(
                item_ids={birthday_id, related_person_id},
                author_username="owner",
                kind=KnowledgeItemKind.PERSON,
            ),
        ]
