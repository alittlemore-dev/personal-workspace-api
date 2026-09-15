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
