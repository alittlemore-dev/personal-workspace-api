from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.files.enums import FilePurpose
from core.files.schemas import StoredFile
from core.files.types import Namespace
from core.knowledge.exceptions import (
    KnowledgeConflictError,
    KnowledgeFileNotFoundError,
)
from core.knowledge.files.schemas import KnowledgeFile
from core.knowledge.files.storages import KnowledgeFilesStorage
from infra.postgresql.models.files import FileModel
from infra.postgresql.models.knowledge.files import KnowledgeItemFileModel


@dataclass(kw_only=True)
class KnowledgeFilesDatabaseStorage(KnowledgeFilesStorage):
    session: AsyncSession
    namespace: Namespace

    async def list_item_files(
        self,
        *,
        item_id: str,
        author_username: str,
    ) -> list[KnowledgeFile]:
        query = (
            select(KnowledgeItemFileModel, FileModel)
            .join(FileModel, FileModel.id == KnowledgeItemFileModel.file_id)
            .where(
                FileModel.namespace == self.namespace,
                KnowledgeItemFileModel.item_id == item_id,
                KnowledgeItemFileModel.author_username == author_username,
            )
            .order_by(
                KnowledgeItemFileModel.kind,
                FileModel.created_at,
                FileModel.id,
            )
        )
        return [
            link.to_domain_schema(metadata=metadata)
            for link, metadata in (await self.session.execute(query)).tuples()
        ]

    async def list_files_for_items(
        self,
        *,
        item_ids: set[str],
        author_username: str,
    ) -> list[KnowledgeFile]:
        if not item_ids:
            return []
        query = (
            select(KnowledgeItemFileModel, FileModel)
            .join(FileModel, FileModel.id == KnowledgeItemFileModel.file_id)
            .where(
                FileModel.namespace == self.namespace,
                KnowledgeItemFileModel.item_id.in_(item_ids),
                KnowledgeItemFileModel.author_username == author_username,
            )
            .order_by(
                KnowledgeItemFileModel.item_id,
                KnowledgeItemFileModel.kind,
                FileModel.created_at,
                FileModel.id,
            )
        )
        return [
            link.to_domain_schema(metadata=metadata)
            for link, metadata in (await self.session.execute(query)).tuples()
        ]

    async def get_file(self, *, file_id: str, author_username: str) -> KnowledgeFile:
        query = (
            select(KnowledgeItemFileModel, FileModel)
            .join(FileModel, FileModel.id == KnowledgeItemFileModel.file_id)
            .where(
                FileModel.namespace == self.namespace,
                KnowledgeItemFileModel.file_id == file_id,
                KnowledgeItemFileModel.author_username == author_username,
            )
        )
        row = (await self.session.execute(query)).tuples().one_or_none()
        if row is None:
            raise KnowledgeFileNotFoundError
        link, metadata = row
        return link.to_domain_schema(metadata=metadata)

    async def create_file(self, *, file: KnowledgeFile) -> KnowledgeFile:
        metadata = FileModel.from_domain_schema(
            StoredFile(
                id=file.id,
                purpose=FilePurpose.ATTACHMENT,
                namespace=self.namespace,
                relative_path=file.relative_path,
                mime_type=file.mime_type,
                size_bytes=file.size_bytes,
                name=file.name,
                original_name=file.original_name,
                original_sha256=file.original_sha256,
                orphaned_at=None,
                created_at=file.created_at,
                updated_at=file.updated_at,
            ),
        )
        link = KnowledgeItemFileModel.from_domain_schema(file=file)
        self.session.add_all([metadata, link])
        try:
            await self.session.flush()
        except IntegrityError as error:
            raise KnowledgeConflictError from error
        return link.to_domain_schema(metadata=metadata)

    async def update_file_name(
        self,
        *,
        file: KnowledgeFile,
        name: str,
        updated_at: datetime,
    ) -> KnowledgeFile:
        linked_file_ids = select(KnowledgeItemFileModel.file_id).where(
            KnowledgeItemFileModel.file_id == file.id,
            KnowledgeItemFileModel.item_id == file.item_id,
            KnowledgeItemFileModel.author_username == file.author_username,
        )
        query = (
            update(FileModel)
            .where(
                FileModel.namespace == self.namespace,
                FileModel.id.in_(linked_file_ids),
            )
            .values(name=name, updated_at=updated_at)
            .returning(FileModel)
        )
        metadata = await self.session.scalar(query)
        if metadata is None:
            raise KnowledgeFileNotFoundError
        return KnowledgeFile(
            id=metadata.id,
            item_id=file.item_id,
            author_username=file.author_username,
            kind=file.kind,
            processing=file.processing,
            relative_path=metadata.relative_path,
            mime_type=metadata.mime_type,
            size_bytes=metadata.size_bytes,
            name=metadata.name,
            original_name=metadata.original_name,
            original_sha256=metadata.original_sha256 or "",
            created_at=metadata.created_at,
            updated_at=metadata.updated_at,
        )

    async def delete_file(self, *, file: KnowledgeFile) -> None:
        namespace_file_ids = select(FileModel.id).where(
            FileModel.namespace == self.namespace,
            FileModel.id == file.id,
        )
        query = (
            delete(KnowledgeItemFileModel)
            .where(
                KnowledgeItemFileModel.file_id.in_(namespace_file_ids),
                KnowledgeItemFileModel.item_id == file.item_id,
                KnowledgeItemFileModel.author_username == file.author_username,
            )
            .returning(KnowledgeItemFileModel.file_id)
        )
        if await self.session.scalar(query) is None:
            raise KnowledgeFileNotFoundError
