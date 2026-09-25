from datetime import UTC, datetime

import pytest
import pytest_asyncio

from core.knowledge.exceptions import (
    KnowledgeConflictError,
    PersonRelationshipTypeNotFoundError,
)
from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.items.schemas import KnowledgeItemCreateParams
from core.knowledge.people.enums import PersonListSort, PersonRelationshipDirection
from core.knowledge.people.schemas import (
    PersonBirthday,
    PersonDetails,
    PersonFilters,
    PersonRelationshipCreateParams,
    PersonRelationshipTypeCreateParams,
    PersonRelationshipTypeUpdateParams,
    PersonRelationshipUpdateParams,
)
from core.knowledge.people.use_cases import PersonRelationshipTypesUseCase
from infra.postgresql.storages.knowledge.items import KnowledgeItemsDatabaseStorage
from infra.postgresql.storages.knowledge.people import PeopleDatabaseStorage
from tests.test_cases import StorageTestCase

CURRENT_DATETIME = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


class TestKnowledgePeopleStorage(StorageTestCase):
    @pytest_asyncio.fixture
    async def relationship_context(self) -> tuple[PeopleDatabaseStorage, str, str]:
        storage = PeopleDatabaseStorage(session=self.db_session)
        first_id = await self.create_person(
            author_username="owner",
            last_name="First",
            first_name="Alice",
        )
        second_id = await self.create_person(
            author_username="owner",
            last_name="Second",
            first_name="Bob",
        )
        return storage, first_id, second_id

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

    async def test_relationship_updates_and_deletion_remain_author_scoped(
        self,
        relationship_context: tuple[PeopleDatabaseStorage, str, str],
    ) -> None:
        storage, first_id, second_id = relationship_context
        relationship_type = await storage.create_relationship_type(
            params=PersonRelationshipTypeCreateParams(
                author_username="owner",
                is_symmetric=False,
                forward_name="manager",
                reverse_name="report",
            ),
        )
        await storage.create_relationships(
            person_id=first_id,
            author_username="owner",
            values=[
                PersonRelationshipCreateParams(
                    related_person_id=second_id,
                    relationship_type_id=relationship_type.id,
                    direction=PersonRelationshipDirection.FORWARD,
                    note="before",
                )
            ],
            relationship_types={relationship_type.id: relationship_type},
            created_at=CURRENT_DATETIME,
        )
        relationship = (
            await storage.list_relationships(
                person_id=first_id,
                author_username="owner",
            )
        )[0]
        changed = PersonRelationshipUpdateParams(
            id=relationship.id,
            related_person_id=second_id,
            relationship_type_id=relationship_type.id,
            direction=PersonRelationshipDirection.REVERSE,
            note="after",
        )

        await storage.update_relationships(
            person_id=first_id,
            author_username="other-owner",
            values=[changed],
            relationship_types={relationship_type.id: relationship_type},
            updated_at=CURRENT_DATETIME,
        )
        assert (
            await storage.list_relationships(
                person_id=first_id,
                author_username="owner",
            )
        )[0].note == "before"

        await storage.update_relationships(
            person_id=first_id,
            author_username="owner",
            values=[changed],
            relationship_types={relationship_type.id: relationship_type},
            updated_at=CURRENT_DATETIME,
        )
        updated = (
            await storage.list_relationships(
                person_id=first_id,
                author_username="owner",
            )
        )[0]
        assert updated.source_person_id == second_id
        assert updated.target_person_id == first_id
        assert updated.note == "after"
        assert await storage.list_related_person_ids(
            person_id=first_id,
            author_username="owner",
        ) == {second_id}
        assert (
            await storage.get_relationships_by_ids(
                relationship_ids={relationship.id},
                author_username="other-owner",
            )
            == []
        )

        await storage.delete_relationships(
            relationship_ids={relationship.id},
            author_username="other-owner",
        )
        assert (
            len(
                await storage.list_relationships(
                    person_id=first_id,
                    author_username="owner",
                )
            )
            == 1
        )
        await storage.delete_relationships(
            relationship_ids={relationship.id},
            author_username="owner",
        )
        assert (
            await storage.list_relationships(
                person_id=first_id,
                author_username="owner",
            )
            == []
        )

    async def test_relationship_type_cannot_be_deleted_while_used(
        self,
        relationship_context: tuple[PeopleDatabaseStorage, str, str],
    ) -> None:
        storage, first_id, second_id = relationship_context
        use_case = PersonRelationshipTypesUseCase(storage=storage)
        relationship_type = await use_case.create_relationship_type(
            params=PersonRelationshipTypeCreateParams(
                author_username="owner",
                is_symmetric=True,
                forward_name="friend",
                reverse_name="",
            ),
            current_datetime=CURRENT_DATETIME,
        )
        assert relationship_type.reverse_name == "friend"
        assert [
            value.id
            for value in await use_case.list_relationship_types(
                author_username="owner",
            )
        ] == [relationship_type.id]
        assert await use_case.list_relationship_types(author_username="other-owner") == []
        with pytest.raises(PersonRelationshipTypeNotFoundError):
            await use_case.update_relationship_type(
                relationship_type_id=relationship_type.id,
                params=PersonRelationshipTypeUpdateParams(
                    is_symmetric=False,
                    forward_name="manager",
                    reverse_name="report",
                ),
                author_username="other-owner",
                current_datetime=CURRENT_DATETIME,
            )

        await storage.create_relationships(
            person_id=first_id,
            author_username="owner",
            values=[
                PersonRelationshipCreateParams(
                    related_person_id=second_id,
                    relationship_type_id=relationship_type.id,
                    direction=PersonRelationshipDirection.FORWARD,
                    note="",
                )
            ],
            relationship_types={relationship_type.id: relationship_type},
            created_at=CURRENT_DATETIME,
        )
        with pytest.raises(KnowledgeConflictError):
            await use_case.delete_relationship_type(
                relationship_type_id=relationship_type.id,
                author_username="owner",
            )
        relationship = (
            await storage.list_relationships(
                person_id=first_id,
                author_username="owner",
            )
        )[0]
        await storage.delete_relationships(
            relationship_ids={relationship.id},
            author_username="owner",
        )
        await use_case.delete_relationship_type(
            relationship_type_id=relationship_type.id,
            author_username="owner",
        )
        assert await storage.list_relationship_types(author_username="owner") == []
