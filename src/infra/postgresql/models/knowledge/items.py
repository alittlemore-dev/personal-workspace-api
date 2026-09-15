from typing import Self

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    literal,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column
from sqlalchemy_dev_utils.mixins.audit import AuditMixin

from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.items.schemas import (
    KnowledgeItem,
    KnowledgeItemCreateParams,
    KnowledgeTag,
    KnowledgeTagCreateParams,
)
from infra.postgresql.models.base import BaseModel, TableArgs
from infra.postgresql.models.mixins.ids import HexUuidIDMixin


class KnowledgeItemModel(HexUuidIDMixin, AuditMixin, BaseModel):
    __tablename__ = "knowledge__knowledge_item_model"

    kind: Mapped[KnowledgeItemKind] = mapped_column(
        Enum(KnowledgeItemKind, native_enum=True, name="knowledge_item_kind_enum"),
        doc="Typed knowledge item discriminator",
    )
    author_username: Mapped[str] = mapped_column(
        String(length=255),
        doc="Username owning the private knowledge item",
    )
    display_name: Mapped[str] = mapped_column(
        String(length=255),
        doc="Server-derived list display name",
    )
    description: Mapped[str] = mapped_column(
        Text,
        doc="Private Markdown description",
    )

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgs:
        return (
            UniqueConstraint(
                cls.id,
                cls.author_username,
                name="knowledge_items_id_author_uniq",
            ),
            Index(
                "knowledge_items_author_kind_updated_id_idx",
                cls.author_username,
                cls.kind,
                cls.updated_at.desc(),
                cls.id.desc(),
            ),
            Index(
                "knowledge_items_author_kind_name_id_idx",
                cls.author_username,
                cls.kind,
                func.lower(cls.display_name).label("display_name_lower"),
                cls.id,
            ),
            Index(
                "knowledge_items_display_name_trgm_idx",
                func.lower(cls.display_name).label("display_name_lower_trgm"),
                postgresql_using="gin",
                postgresql_ops={"display_name_lower_trgm": "gin_trgm_ops"},
            ),
            CheckConstraint(
                func.char_length(cls.description) <= literal(100_000),
                name="knowledge_items_description_length_check",
            ),
        )

    @classmethod
    def from_create_params(cls, *, params: KnowledgeItemCreateParams) -> Self:
        return cls(
            kind=params.kind,
            author_username=params.author_username,
            display_name=params.display_name,
            description=params.description,
        )

    def to_domain_schema(self, *, tags: list[KnowledgeTag]) -> KnowledgeItem:
        return KnowledgeItem(
            id=self.id,
            kind=self.kind,
            author_username=self.author_username,
            display_name=self.display_name,
            description=self.description,
            tags=tags,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class KnowledgeTagModel(HexUuidIDMixin, AuditMixin, BaseModel):
    __tablename__ = "knowledge__knowledge_tag_model"

    author_username: Mapped[str] = mapped_column(
        String(length=255),
        doc="Username owning the private knowledge tag",
    )
    name: Mapped[str] = mapped_column(String(length=255), doc="Author-scoped tag name")

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgs:
        return (
            UniqueConstraint(cls.id, cls.author_username, name="knowledge_tags_id_author_uniq"),
            Index(
                "knowledge_tags_author_name_lower_uniq",
                cls.author_username,
                func.lower(cls.name).label("name_lower"),
                unique=True,
            ),
            Index(
                "knowledge_tags_author_name_id_idx",
                cls.author_username,
                func.lower(cls.name).label("name_lower"),
                cls.id,
            ),
            Index(
                "knowledge_tags_name_trgm_idx",
                func.lower(cls.name).label("name_lower_trgm"),
                postgresql_using="gin",
                postgresql_ops={"name_lower_trgm": "gin_trgm_ops"},
            ),
        )

    @classmethod
    def from_create_params(cls, *, params: KnowledgeTagCreateParams) -> Self:
        return cls(author_username=params.author_username, name=params.name)

    def to_domain_schema(self) -> KnowledgeTag:
        return KnowledgeTag(
            id=self.id,
            author_username=self.author_username,
            name=self.name,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class KnowledgeItemTagModel(AuditMixin, BaseModel):
    __tablename__ = "knowledge__knowledge_item_tag_model"

    item_id: Mapped[str] = mapped_column(String(length=32), primary_key=True)
    tag_id: Mapped[str] = mapped_column(String(length=32), primary_key=True)
    author_username: Mapped[str] = mapped_column(String(length=255))

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgs:
        return (
            ForeignKeyConstraint(
                [cls.item_id, cls.author_username],
                [KnowledgeItemModel.id, KnowledgeItemModel.author_username],
                ondelete="CASCADE",
                name="knowledge_item_tags_item_author_fk",
            ),
            ForeignKeyConstraint(
                [cls.tag_id, cls.author_username],
                [KnowledgeTagModel.id, KnowledgeTagModel.author_username],
                ondelete="RESTRICT",
                name="knowledge_item_tags_tag_author_fk",
            ),
            Index(
                "knowledge_item_tags_author_tag_item_idx",
                cls.author_username,
                cls.tag_id,
                cls.item_id,
            ),
        )
