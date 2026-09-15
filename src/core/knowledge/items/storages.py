from abc import ABC, abstractmethod
from datetime import datetime

from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.items.schemas import (
    KnowledgeItem,
    KnowledgeItemCreateParams,
    KnowledgeItemUpdateParams,
    KnowledgeTag,
    KnowledgeTagCreateParams,
)


class KnowledgeItemsStorage(ABC):
    @abstractmethod
    async def get_item(
        self,
        *,
        item_id: str,
        author_username: str,
        kind: KnowledgeItemKind,
    ) -> KnowledgeItem:
        raise NotImplementedError

    @abstractmethod
    async def get_item_for_author(
        self,
        *,
        item_id: str,
        author_username: str,
    ) -> KnowledgeItem:
        raise NotImplementedError

    @abstractmethod
    async def get_items_by_ids(
        self,
        *,
        item_ids: set[str],
        author_username: str,
        kind: KnowledgeItemKind,
    ) -> list[KnowledgeItem]:
        raise NotImplementedError

    @abstractmethod
    async def create_item(self, *, params: KnowledgeItemCreateParams) -> KnowledgeItem:
        raise NotImplementedError

    @abstractmethod
    async def update_item(
        self,
        *,
        item: KnowledgeItem,
        params: KnowledgeItemUpdateParams,
        updated_at: datetime,
    ) -> KnowledgeItem:
        raise NotImplementedError

    @abstractmethod
    async def delete_item(
        self,
        *,
        item_id: str,
        author_username: str,
        kind: KnowledgeItemKind,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def touch_items(
        self,
        *,
        item_ids: set[str],
        author_username: str,
        kind: KnowledgeItemKind,
        updated_at: datetime,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def replace_item_tags(
        self,
        *,
        item_id: str,
        author_username: str,
        tag_ids: list[str],
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_tags(
        self,
        *,
        author_username: str,
        search_query: str | None,
    ) -> list[KnowledgeTag]:
        raise NotImplementedError

    @abstractmethod
    async def get_tag(self, *, tag_id: str, author_username: str) -> KnowledgeTag:
        raise NotImplementedError

    @abstractmethod
    async def get_tags_by_ids(
        self,
        *,
        tag_ids: set[str],
        author_username: str,
    ) -> list[KnowledgeTag]:
        raise NotImplementedError

    @abstractmethod
    async def find_tag_by_name(
        self,
        *,
        name: str,
        author_username: str,
    ) -> KnowledgeTag | None:
        raise NotImplementedError

    @abstractmethod
    async def create_tag(self, *, params: KnowledgeTagCreateParams) -> KnowledgeTag:
        raise NotImplementedError

    @abstractmethod
    async def update_tag(
        self,
        *,
        tag: KnowledgeTag,
        name: str,
        updated_at: datetime,
    ) -> KnowledgeTag:
        raise NotImplementedError

    @abstractmethod
    async def is_tag_used(self, *, tag_id: str, author_username: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def delete_tag(self, *, tag_id: str, author_username: str) -> None:
        raise NotImplementedError
