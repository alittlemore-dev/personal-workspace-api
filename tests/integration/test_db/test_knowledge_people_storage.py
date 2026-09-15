from datetime import UTC, datetime

import pytest

from core.knowledge.exceptions import KnowledgeConflictError
from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.items.schemas import KnowledgeItemCreateParams
from core.knowledge.people.enums import PersonListSort, PersonRelationshipDirection
from core.knowledge.people.schemas import (
    PersonBirthday,
    PersonDetails,
    PersonFilters,
    PersonRelationshipCreateParams,
    PersonRelationshipTypeCreateParams,
)
from infra.postgresql.storages.knowledge.items import KnowledgeItemsDatabaseStorage
from infra.postgresql.storages.knowledge.people import PeopleDatabaseStorage
from tests.test_cases import StorageTestCase

CURRENT_DATETIME = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


class TestKnowledgePeopleStorage(StorageTestCase):
    async def create_person(
        self,
        *,
        author_username: str,
        last_name: str,
        first_name: str,
        email: str = "",
        birthday: PersonBirthday | None = None,
    ) -> str:
        item = await KnowledgeItemsDatabaseStorage(session=self.db_session).create_item(
            params=KnowledgeItemCreateParams(
                kind=KnowledgeItemKind.PERSON,
                author_username=author_username,
                display_name=f"{last_name} {first_name}",
                description="",
            ),
        )
        await PeopleDatabaseStorage(session=self.db_session).create_details(
            details=PersonDetails(
                item_id=item.id,
                last_name=last_name,
                first_name=first_name,
                middle_name="",
                email=email,
                phone="",
                telegram="",
                birthday=birthday,
            ),
            author_username=author_username,
        )
        return item.id

    async def test_search_sort_pagination_and_birthdays_are_author_scoped(self) -> None:
        storage = PeopleDatabaseStorage(session=self.db_session)
        alpha_id = await self.create_person(
            author_username="owner",
            last_name="Alpha",
            first_name="Anna",
            email="anna@example.com",
            birthday=PersonBirthday(day=31, month=7, year=None),
        )
        await self.create_person(
            author_username="owner",
            last_name="Beta",
            first_name="Boris",
            email="boris@example.com",
            birthday=PersonBirthday(day=1, month=8, year=None),
        )
        await self.create_person(
            author_username="other-owner",
            last_name="Foreign",
            first_name="Person",
            email="foreign@example.com",
            birthday=PersonBirthday(day=2, month=8, year=None),
        )

        matches, total_count = await storage.list_person_page(
            filters=PersonFilters(
                page=1,
                page_size=1,
                sort=PersonListSort.NAME_ASC,
                search_query="EXAMPLE.COM",
                tag_ids=(),
                author_username="owner",
            ),
        )
        birthdays = await storage.list_birthday_details_for_months(
            months=(7,),
            author_username="owner",
        )

        assert matches == [alpha_id]
        assert total_count == 2
        assert [value.item_id for value in birthdays] == [alpha_id]

    async def test_directional_relationship_round_trips_from_both_people(self) -> None:
        storage = PeopleDatabaseStorage(session=self.db_session)
        manager_id = await self.create_person(
            author_username="owner",
            last_name="Manager",
            first_name="Mary",
        )
        report_id = await self.create_person(
            author_username="owner",
            last_name="Report",
            first_name="Robert",
        )
        relationship_type = await storage.create_relationship_type(
            params=PersonRelationshipTypeCreateParams(
                author_username="owner",
                is_symmetric=False,
                forward_name="manager",
                reverse_name="report",
            ),
        )
        values = [
            PersonRelationshipCreateParams(
                related_person_id=report_id,
                relationship_type_id=relationship_type.id,
                direction=PersonRelationshipDirection.FORWARD,
                note="",
            ),
        ]

        await storage.create_relationships(
            person_id=manager_id,
            author_username="owner",
            values=values,
            relationship_types={relationship_type.id: relationship_type},
            created_at=CURRENT_DATETIME,
        )
        manager_relationship = (
            await storage.list_relationships(
                person_id=manager_id,
                author_username="owner",
            )
        )[0]
        report_relationship = (
            await storage.list_relationships(
                person_id=report_id,
                author_username="owner",
            )
        )[0]

        assert manager_relationship.label_for(person_id=manager_id) == "manager"
        assert report_relationship.label_for(person_id=report_id) == "report"
        assert (
            await storage.list_relationships(
                person_id=manager_id,
                author_username="other-owner",
            )
            == []
        )

        with pytest.raises(KnowledgeConflictError):
            await storage.create_relationships(
                person_id=report_id,
                author_username="owner",
                values=[
                    PersonRelationshipCreateParams(
                        related_person_id=manager_id,
                        relationship_type_id=relationship_type.id,
                        direction=PersonRelationshipDirection.FORWARD,
                        note="duplicate unordered pair",
                    ),
                ],
                relationship_types={relationship_type.id: relationship_type},
                created_at=CURRENT_DATETIME,
            )
