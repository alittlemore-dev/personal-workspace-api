from dataclasses import replace
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from core.knowledge.exceptions import (
    KnowledgeConflictError,
    KnowledgeItemNotFoundError,
    KnowledgeTagNotFoundError,
)
from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.items.schemas import (
    KnowledgeItemCreateParams,
    KnowledgeItemUpdateParams,
    KnowledgeTagCreateParams,
    KnowledgeTagUpdateParams,
)
from core.knowledge.items.use_cases import KnowledgeTagsUseCase
from infra.postgresql.storages.knowledge.items import KnowledgeItemsDatabaseStorage
from tests.test_cases import StorageTestCase

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


class TestKnowledgeItemsStorage(StorageTestCase):
    @pytest_asyncio.fixture(autouse=True)
    async def setup(self) -> None:
        self.storage = KnowledgeItemsDatabaseStorage(session=self.db_session)
        self.use_case = KnowledgeTagsUseCase(storage=self.storage)
        self.item = await self.storage.create_item(
            params=KnowledgeItemCreateParams(
                kind=KnowledgeItemKind.PERSON,
                author_username="owner",
                display_name="Private person",
                description="Private notes",
            ),
        )

    async def test_item_reads_and_tags_are_scoped_to_author_and_kind(self) -> None:
        own_tag = await self.storage.create_tag(
            params=KnowledgeTagCreateParams(name="Work", author_username="owner"),
        )
        foreign_tag = await self.storage.create_tag(
            params=KnowledgeTagCreateParams(name="Work", author_username="other-owner"),
        )
        await self.storage.replace_item_tags(
            item_id=self.item.id,
            author_username="owner",
            tag_ids=[own_tag.id, own_tag.id],
        )

        loaded = await self.storage.get_item(
            item_id=self.item.id,
            author_username="owner",
            kind=KnowledgeItemKind.PERSON,
        )
        assert loaded.description == "Private notes"
        assert [tag.id for tag in loaded.tags] == [own_tag.id]
        assert [
            value.id
            for value in await self.storage.get_items_by_ids(
                item_ids={self.item.id},
                author_username="owner",
                kind=KnowledgeItemKind.PERSON,
            )
        ] == [self.item.id]
        assert (
            await self.storage.get_items_by_ids(
                item_ids={self.item.id},
                author_username="other-owner",
                kind=KnowledgeItemKind.PERSON,
            )
            == []
        )
        assert [
            tag.id
            for tag in await self.storage.get_tags_by_ids(
                tag_ids={own_tag.id, foreign_tag.id},
                author_username="owner",
            )
        ] == [own_tag.id]

        for author, kind in (
            ("other-owner", KnowledgeItemKind.PERSON),
            ("owner", KnowledgeItemKind.DATE),
        ):
            with pytest.raises(KnowledgeItemNotFoundError):
                await self.storage.get_item(
                    item_id=self.item.id,
                    author_username=author,
                    kind=kind,
                )
        with pytest.raises(KnowledgeItemNotFoundError):
            await self.storage.get_item_for_author(
                item_id=self.item.id,
                author_username="other-owner",
            )
        with pytest.raises(KnowledgeTagNotFoundError):
            await self.storage.get_tag(tag_id=own_tag.id, author_username="other-owner")

    async def test_item_mutations_cannot_change_another_authors_row(self) -> None:
        with pytest.raises(KnowledgeItemNotFoundError):
            await self.storage.update_item(
                item=replace(self.item, author_username="other-owner"),
                params=KnowledgeItemUpdateParams(
                    display_name="Changed",
                    description="Changed",
                ),
                updated_at=NOW,
            )
        with pytest.raises(KnowledgeItemNotFoundError):
            await self.storage.delete_item(
                item_id=self.item.id,
                author_username="other-owner",
                kind=KnowledgeItemKind.PERSON,
            )
        assert (
            await self.storage.get_item_for_author(
                item_id=self.item.id,
                author_username="owner",
            )
        ).display_name == "Private person"

    async def test_tag_rules_reject_duplicates_and_deletion_while_used(self) -> None:
        tag = await self.use_case.create_tag(
            params=KnowledgeTagCreateParams(name="  Work  ", author_username="owner"),
        )
        await self.use_case.create_tag(
            params=KnowledgeTagCreateParams(name="Work", author_username="other-owner"),
        )

        assert tag.name == "Work"
        assert [
            value.id
            for value in await self.use_case.list_tags(
                author_username="owner",
                search_query="WORK",
            )
        ] == [tag.id]
        with pytest.raises(KnowledgeConflictError):
            await self.use_case.create_tag(
                params=KnowledgeTagCreateParams(name="work", author_username="owner"),
            )
        with pytest.raises(KnowledgeTagNotFoundError):
            await self.use_case.update_tag(
                tag_id=tag.id,
                params=KnowledgeTagUpdateParams(name="Changed"),
                author_username="other-owner",
                current_datetime=NOW,
            )

        await self.storage.replace_item_tags(
            item_id=self.item.id,
            author_username="owner",
            tag_ids=[tag.id],
        )
        with pytest.raises(KnowledgeConflictError):
            await self.use_case.delete_tag(tag_id=tag.id, author_username="owner")
        await self.storage.replace_item_tags(
            item_id=self.item.id,
            author_username="owner",
            tag_ids=[],
        )
        await self.use_case.delete_tag(tag_id=tag.id, author_username="owner")
        with pytest.raises(KnowledgeTagNotFoundError):
            await self.storage.get_tag(tag_id=tag.id, author_username="owner")
