from dataclasses import dataclass
from datetime import datetime

from core.knowledge.exceptions import KnowledgeTagNotFoundError
from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.items.schemas import (
    KnowledgeItem,
    KnowledgeItemCreateParams,
    KnowledgeItemUpdateParams,
)
from core.knowledge.items.storages import KnowledgeItemsStorage


@dataclass(kw_only=True, slots=True, frozen=True)
class KnowledgeItemCrudService:
    storage: KnowledgeItemsStorage

    async def get_item(
        self,
        *,
        item_id: str,
        author_username: str,
        kind: KnowledgeItemKind,
    ) -> KnowledgeItem:
        return await self.storage.get_item(
            item_id=item_id,
            author_username=author_username,
            kind=kind,
        )

    async def create_item(
        self,
        *,
        params: KnowledgeItemCreateParams,
    ) -> KnowledgeItem:
        return await self.storage.create_item(params=params)

    async def update_item(
        self,
        *,
        item: KnowledgeItem,
        params: KnowledgeItemUpdateParams,
        tag_ids: list[str],
        updated_at: datetime,
    ) -> KnowledgeItem:
        tags = await self.storage.get_tags_by_ids(
            tag_ids=set(tag_ids),
            author_username=item.author_username,
        )
        if len(tags) != len(set(tag_ids)):
            raise KnowledgeTagNotFoundError
        updated_item = await self.storage.update_item(
            item=item,
            params=params,
            updated_at=updated_at,
        )
        await self.storage.replace_item_tags(
            item_id=item.id,
            author_username=item.author_username,
            tag_ids=tag_ids,
        )
        return updated_item

    async def delete_item(
        self,
        *,
        item_id: str,
        author_username: str,
        kind: KnowledgeItemKind,
    ) -> None:
        await self.storage.delete_item(
            item_id=item_id,
            author_username=author_username,
            kind=kind,
        )
