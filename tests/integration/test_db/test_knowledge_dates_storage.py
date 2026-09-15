from core.knowledge.dates.enums import KnowledgeDateListSort
from core.knowledge.dates.schemas import (
    KnowledgeDateDetails,
    KnowledgeDateFilters,
    KnowledgeDateValue,
)
from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.items.schemas import KnowledgeItemCreateParams
from core.knowledge.people.schemas import PersonDetails
from infra.postgresql.storages.knowledge.dates import KnowledgeDatesDatabaseStorage
from infra.postgresql.storages.knowledge.items import KnowledgeItemsDatabaseStorage
from infra.postgresql.storages.knowledge.people import PeopleDatabaseStorage
from tests.test_cases import StorageTestCase


class TestKnowledgeDatesStorage(StorageTestCase):
    async def create_item(
        self,
        *,
        kind: KnowledgeItemKind,
        author_username: str,
        display_name: str,
    ) -> str:
        item = await KnowledgeItemsDatabaseStorage(session=self.db_session).create_item(
            params=KnowledgeItemCreateParams(
                kind=kind,
                author_username=author_username,
                display_name=display_name,
                description="",
            ),
        )
        return item.id

    async def create_date(
        self,
        *,
        author_username: str,
        display_name: str,
        day: int,
        month: int,
    ) -> str:
        item_id = await self.create_item(
            kind=KnowledgeItemKind.DATE,
            author_username=author_username,
            display_name=display_name,
        )
        await KnowledgeDatesDatabaseStorage(session=self.db_session).create_details(
            details=KnowledgeDateDetails(
                item_id=item_id,
                date=KnowledgeDateValue(day=day, month=month, year=None),
            ),
            author_username=author_username,
        )
        return item_id

    async def create_person(self, *, author_username: str) -> str:
        item_id = await self.create_item(
            kind=KnowledgeItemKind.PERSON,
            author_username=author_username,
            display_name="Ivanov Ivan",
        )
        await PeopleDatabaseStorage(session=self.db_session).create_details(
            details=PersonDetails(
                item_id=item_id,
                last_name="Ivanov",
                first_name="Ivan",
                middle_name="",
                email="",
                phone="",
                telegram="",
                birthday=None,
            ),
            author_username=author_username,
        )
        return item_id

    async def test_filters_ordering_links_and_month_projection_are_author_scoped(self) -> None:
        storage = KnowledgeDatesDatabaseStorage(session=self.db_session)
        person_id = await self.create_person(author_username="owner")
        january_id = await self.create_date(
            author_username="owner",
            display_name="New year",
            day=1,
            month=1,
        )
        december_id = await self.create_date(
            author_username="owner",
            display_name="Anniversary",
            day=31,
            month=12,
        )
        await self.create_date(
            author_username="other-owner",
            display_name="Foreign anniversary",
            day=2,
            month=12,
        )
        await storage.replace_person_links(
            date_id=december_id,
            person_ids=[person_id],
            author_username="owner",
        )

        first_page, total_count = await storage.list_date_page(
            filters=KnowledgeDateFilters(
                page=1,
                page_size=1,
                sort=KnowledgeDateListSort.DATE_ASC,
                search_query=None,
                tag_ids=(),
                related_person_id=None,
                author_username="owner",
            ),
        )
        related, related_count = await storage.list_date_page(
            filters=KnowledgeDateFilters(
                page=1,
                page_size=20,
                sort=KnowledgeDateListSort.DATE_DESC,
                search_query="ANNIVERSARY",
                tag_ids=(),
                related_person_id=person_id,
                author_username="owner",
            ),
        )
        month_details = await storage.list_details_for_months(
            months=(12,),
            author_username="owner",
        )

        assert first_page == [january_id]
        assert total_count == 2
        assert related == [december_id]
        assert related_count == 1
        assert [value.item_id for value in month_details] == [december_id]
        assert await storage.list_date_ids_for_person(
            person_id=person_id,
            author_username="owner",
        ) == [december_id]

    async def test_deleting_person_cascades_link_but_keeps_date(self) -> None:
        item_storage = KnowledgeItemsDatabaseStorage(session=self.db_session)
        date_storage = KnowledgeDatesDatabaseStorage(session=self.db_session)
        person_id = await self.create_person(author_username="owner")
        date_id = await self.create_date(
            author_username="owner",
            display_name="Anniversary",
            day=31,
            month=12,
        )
        await date_storage.replace_person_links(
            date_id=date_id,
            person_ids=[person_id],
            author_username="owner",
        )

        await item_storage.delete_item(
            item_id=person_id,
            author_username="owner",
            kind=KnowledgeItemKind.PERSON,
        )

        assert (
            await date_storage.list_person_links(
                date_ids={date_id},
                author_username="owner",
            )
            == []
        )
        assert (
            await date_storage.get_details(
                item_id=date_id,
                author_username="owner",
            )
        ).item_id == date_id
