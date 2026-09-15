from datetime import UTC, datetime
from unittest.mock import Mock

from core.knowledge.items.schemas import KnowledgeTag, KnowledgeTagUpdateParams
from core.knowledge.items.storages import KnowledgeItemsStorage
from core.knowledge.items.use_cases import KnowledgeTagsUseCase
from tests.test_cases import TestCase

CURRENT_DATETIME = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


class TestKnowledgeTagsUseCase(TestCase):
    async def test_update_reuses_supplied_datetime_for_persistence(self) -> None:
        storage = Mock(spec=KnowledgeItemsStorage)
        use_case = KnowledgeTagsUseCase(storage=storage)
        tag = KnowledgeTag(
            id=self.factory.core.hex_id(1),
            author_username="owner",
            name="Work",
            created_at=CURRENT_DATETIME,
            updated_at=CURRENT_DATETIME,
        )
        storage.get_tag.return_value = tag
        storage.find_tag_by_name.return_value = None
        storage.update_tag.return_value = tag

        await use_case.update_tag(
            tag_id=tag.id,
            params=KnowledgeTagUpdateParams(name="Career"),
            author_username="owner",
            current_datetime=CURRENT_DATETIME,
        )

        assert storage.update_tag.await_args.kwargs["updated_at"] == CURRENT_DATETIME
