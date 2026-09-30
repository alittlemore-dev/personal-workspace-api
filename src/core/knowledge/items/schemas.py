from dataclasses import dataclass
from datetime import datetime

from core.knowledge.items.enums import KnowledgeItemKind


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeTag:
    id: str
    author_username: str
    name: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeItem:
    id: str
    kind: KnowledgeItemKind
    author_username: str
    display_name: str
    description: str
    tags: list[KnowledgeTag]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeItemCreateParams:
    kind: KnowledgeItemKind
    author_username: str
    display_name: str
    description: str


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeItemUpdateParams:
    display_name: str
    description: str


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeTagCreateParams:
    name: str
    author_username: str


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeTagUpdateParams:
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ListKnowledgeTagsParams:
    author_username: str
    search_query: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateKnowledgeTagParams:
    tag_id: str
    data: KnowledgeTagUpdateParams
    author_username: str
    current_datetime: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeTagTargetParams:
    tag_id: str
    author_username: str
