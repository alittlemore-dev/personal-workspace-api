from datetime import UTC, date, datetime

import pytest

from core.knowledge.exceptions import InvalidKnowledgeDataError
from core.knowledge.people.enums import PersonRelationshipDirection
from core.knowledge.people.schemas import (
    PersonBirthday,
    PersonDetails,
    PersonRelationship,
    PersonRelationshipType,
)
from tests.test_cases import TestCase


class TestPeopleDomain(TestCase):
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)

    def test_birthday_accepts_unknown_year_and_leap_day(self) -> None:
        birthday = PersonBirthday(day=29, month=2, year=None)

        birthday.validate(today=date(2026, 7, 27))

    @pytest.mark.parametrize(
        ("day", "month", "year"),
        [
            (31, 4, None),
            (29, 2, 2025),
            (0, 1, None),
            (1, 13, None),
        ],
    )
    def test_birthday_rejects_impossible_combinations(
        self,
        day: int,
        month: int,
        year: int | None,
    ) -> None:
        with pytest.raises(InvalidKnowledgeDataError):
            PersonBirthday(day=day, month=month, year=year)

    def test_birthday_rejects_future_full_date(self) -> None:
        birthday = PersonBirthday(day=28, month=7, year=2026)

        with pytest.raises(InvalidKnowledgeDataError):
            birthday.validate(today=date(2026, 7, 27))

    def test_person_details_builds_display_name_without_extra_spaces(self) -> None:
        details = PersonDetails(
            item_id=self.factory.core.hex_id(1),
            last_name="Иванов",
            first_name="Иван",
            middle_name="",
            email="",
            phone="",
            telegram="",
            birthday=None,
        )

        assert details.display_name == "Иванов Иван"

    def test_directional_relationship_projects_both_sides(self) -> None:
        relationship_type = PersonRelationshipType(
            id=self.factory.core.hex_id(3),
            author_username="owner",
            is_symmetric=False,
            forward_name="руководитель",
            reverse_name="подчинённый",
            created_at=self.timestamp,
            updated_at=self.timestamp,
        )
        relationship = PersonRelationship(
            id=self.factory.core.hex_id(4),
            author_username="owner",
            source_person_id=self.factory.core.hex_id(1),
            target_person_id=self.factory.core.hex_id(2),
            relationship_type=relationship_type,
            note="",
            created_at=self.timestamp,
            updated_at=self.timestamp,
        )

        assert relationship.direction_for(person_id=self.factory.core.hex_id(1)) == (
            PersonRelationshipDirection.FORWARD
        )
        assert relationship.label_for(person_id=self.factory.core.hex_id(1)) == "руководитель"
        assert relationship.direction_for(person_id=self.factory.core.hex_id(2)) == (
            PersonRelationshipDirection.REVERSE
        )
        assert relationship.label_for(person_id=self.factory.core.hex_id(2)) == "подчинённый"

    def test_relationship_rejects_self_link(self) -> None:
        relationship_type = PersonRelationshipType(
            id=self.factory.core.hex_id(3),
            author_username="owner",
            is_symmetric=True,
            forward_name="друг",
            reverse_name="друг",
            created_at=self.timestamp,
            updated_at=self.timestamp,
        )

        with pytest.raises(InvalidKnowledgeDataError):
            PersonRelationship(
                id=self.factory.core.hex_id(4),
                author_username="owner",
                source_person_id=self.factory.core.hex_id(1),
                target_person_id=self.factory.core.hex_id(1),
                relationship_type=relationship_type,
                note="",
                created_at=self.timestamp,
                updated_at=self.timestamp,
            )

    def test_symmetric_relationship_uses_explicit_equal_labels_for_both_sides(self) -> None:
        relationship_type = PersonRelationshipType(
            id=self.factory.core.hex_id(3),
            author_username="owner",
            is_symmetric=True,
            forward_name="друг",
            reverse_name="друг",
            created_at=self.timestamp,
            updated_at=self.timestamp,
        )
        relationship = PersonRelationship(
            id=self.factory.core.hex_id(4),
            author_username="owner",
            source_person_id=self.factory.core.hex_id(1),
            target_person_id=self.factory.core.hex_id(2),
            relationship_type=relationship_type,
            note="",
            created_at=self.timestamp,
            updated_at=self.timestamp,
        )

        assert relationship.label_for(person_id=self.factory.core.hex_id(1)) == "друг"
        assert relationship.label_for(person_id=self.factory.core.hex_id(2)) == "друг"
