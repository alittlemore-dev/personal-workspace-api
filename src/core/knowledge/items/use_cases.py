from dataclasses import dataclass

from core.knowledge.exceptions import (
    InvalidKnowledgeDataError,
    KnowledgeConflictError,
)
from core.knowledge.items.schemas import (
    KnowledgeTag,
    KnowledgeTagCreateParams,
    KnowledgeTagTargetParams,
    ListKnowledgeTagsParams,
    UpdateKnowledgeTagParams,
)
from core.knowledge.items.storages import KnowledgeItemsStorage


@dataclass(kw_only=True, slots=True, frozen=True)
class KnowledgeTagsUseCase:
    storage: KnowledgeItemsStorage

    async def list_tags(self, *, params: ListKnowledgeTagsParams) -> list[KnowledgeTag]:
        return await self.storage.list_tags(
            author_username=params.author_username,
            search_query=params.search_query,
        )

    async def create_tag(self, *, params: KnowledgeTagCreateParams) -> KnowledgeTag:
        name = params.name.strip()
        if not name:
            raise InvalidKnowledgeDataError
        existing = await self.storage.find_tag_by_name(
            name=name,
            author_username=params.author_username,
        )
        if existing is not None:
            raise KnowledgeConflictError
        return await self.storage.create_tag(
            params=KnowledgeTagCreateParams(
                name=name,
                author_username=params.author_username,
            ),
        )

    async def update_tag(self, *, params: UpdateKnowledgeTagParams) -> KnowledgeTag:
        tag = await self.storage.get_tag(
            tag_id=params.tag_id,
            author_username=params.author_username,
        )
        name = params.data.name.strip()
        if not name:
            raise InvalidKnowledgeDataError
        duplicate = await self.storage.find_tag_by_name(
            name=name,
            author_username=params.author_username,
        )
        if duplicate is not None and duplicate.id != tag.id:
            raise KnowledgeConflictError
        return await self.storage.update_tag(
            tag=tag,
            name=name,
            updated_at=params.current_datetime,
        )

    async def delete_tag(self, *, params: KnowledgeTagTargetParams) -> None:
        await self.storage.get_tag(tag_id=params.tag_id, author_username=params.author_username)
        if await self.storage.is_tag_used(
            tag_id=params.tag_id,
            author_username=params.author_username,
        ):
            raise KnowledgeConflictError
        await self.storage.delete_tag(tag_id=params.tag_id, author_username=params.author_username)
