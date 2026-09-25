from datetime import UTC, datetime

import pytest_asyncio
from httpx import codes

from core.knowledge.items.schemas import (
    KnowledgeTag,
    KnowledgeTagCreateParams,
    KnowledgeTagUpdateParams,
)
from tests.test_cases import ApiTestCase
from tests.unit.conftest import TEST_USERNAME

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


class TestKnowledgeTagsApi(ApiTestCase):
    @pytest_asyncio.fixture(autouse=True)
    async def setup(self) -> None:
        self.use_case = await self.container.get_knowledge_tags_use_case()
        self.tag = KnowledgeTag(
            id="1" * 32,
            author_username=TEST_USERNAME,
            name="Work",
            created_at=NOW,
            updated_at=NOW,
        )

    def test_list_and_create_use_current_author(self) -> None:
        self.use_case.list_tags.return_value = [self.tag]
        self.use_case.create_tag.return_value = self.tag

        listed = self.api.client.get("/api/knowledge/tags", params={"searchQuery": "Work"})
        created = self.api.client.post("/api/knowledge/tags", json={"name": "Work"})

        self.asserts.status(response=listed, expected_status=codes.OK)
        self.asserts.status(response=created, expected_status=codes.CREATED)
        assert listed.json()["tags"][0]["id"] == self.tag.id
        assert created.json()["id"] == self.tag.id
        self.use_case.list_tags.assert_awaited_once_with(
            author_username=TEST_USERNAME,
            search_query="Work",
        )
        self.use_case.create_tag.assert_awaited_once_with(
            params=KnowledgeTagCreateParams(name="Work", author_username=TEST_USERNAME),
        )

    def test_rename_and_delete_use_current_author(self) -> None:
        self.use_case.update_tag.return_value = self.tag

        renamed = self.api.client.put(
            f"/api/knowledge/tags/{self.tag.id}",
            json={"name": "Work"},
        )
        deleted = self.api.client.delete(f"/api/knowledge/tags/{self.tag.id}")

        self.asserts.status(response=renamed, expected_status=codes.OK)
        self.asserts.status(response=deleted, expected_status=codes.NO_CONTENT)
        self.use_case.update_tag.assert_awaited_once_with(
            tag_id=self.tag.id,
            params=KnowledgeTagUpdateParams(name="Work"),
            author_username=TEST_USERNAME,
            current_datetime=NOW,
        )
        self.use_case.delete_tag.assert_awaited_once_with(
            tag_id=self.tag.id,
            author_username=TEST_USERNAME,
        )
