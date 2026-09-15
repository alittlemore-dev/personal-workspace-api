from typing import Self

from sqlalchemy import Enum, ForeignKeyConstraint, Index, String
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from core.knowledge.files.enums import KnowledgeFileKind, KnowledgeFileProcessing
from core.knowledge.files.schemas import KnowledgeFile
from infra.postgresql.models.base import BaseModel, TableArgs
from infra.postgresql.models.files import FileModel
from infra.postgresql.models.knowledge.items import KnowledgeItemModel


class KnowledgeItemFileModel(BaseModel):
    __tablename__ = "knowledge__knowledge_item_file_model"

    file_id: Mapped[str] = mapped_column(String(length=32), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(length=32))
    author_username: Mapped[str] = mapped_column(String(length=255))
    kind: Mapped[KnowledgeFileKind] = mapped_column(
        Enum(KnowledgeFileKind, native_enum=True, name="knowledge_file_kind_enum"),
    )
    processing: Mapped[KnowledgeFileProcessing] = mapped_column(
        Enum(
            KnowledgeFileProcessing,
            native_enum=True,
            name="knowledge_file_processing_enum",
        ),
    )

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgs:
        return (
            ForeignKeyConstraint(
                [cls.file_id],
                [FileModel.id],
                ondelete="RESTRICT",
                name="knowledge_item_files_file_fk",
            ),
            ForeignKeyConstraint(
                [cls.item_id, cls.author_username],
                [KnowledgeItemModel.id, KnowledgeItemModel.author_username],
                ondelete="RESTRICT",
                name="knowledge_item_files_item_author_fk",
            ),
            Index(
                "knowledge_item_files_author_item_kind_file_idx",
                cls.author_username,
                cls.item_id,
                cls.kind,
                cls.file_id,
            ),
            Index(
                "knowledge_item_files_one_person_photo_idx",
                cls.author_username,
                cls.item_id,
                unique=True,
                postgresql_where=cls.kind == KnowledgeFileKind.PERSON_PHOTO,
            ),
        )

    @classmethod
    def from_domain_schema(cls, *, file: KnowledgeFile) -> Self:
        return cls(
            file_id=file.id,
            item_id=file.item_id,
            author_username=file.author_username,
            kind=file.kind,
            processing=file.processing,
        )

    def to_domain_schema(self, *, metadata: FileModel) -> KnowledgeFile:
        return KnowledgeFile(
            id=metadata.id,
            item_id=self.item_id,
            author_username=self.author_username,
            kind=self.kind,
            processing=self.processing,
            relative_path=metadata.relative_path,
            mime_type=metadata.mime_type,
            size_bytes=metadata.size_bytes,
            name=metadata.name,
            original_name=metadata.original_name,
            original_sha256=metadata.original_sha256 or "",
            created_at=metadata.created_at,
            updated_at=metadata.updated_at,
        )
