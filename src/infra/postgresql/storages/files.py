from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from core.exceptions import EntryNotFoundError
from core.files.enums import FilePurpose
from core.files.exceptions import NamespaceNotAllowedError
from core.files.schemas import StoredFile, StoredFiles
from core.files.storages import FileStorage
from core.files.types import Namespace
from infra.postgresql.models import FileModel
from infra.postgresql.models.knowledge.files import KnowledgeItemFileModel


@dataclass(kw_only=True)
class FilesDatabaseStorage(FileStorage):
    session: AsyncSession

    @staticmethod
    def file_usage_exists(
        file_id: str | ColumnElement[str] | InstrumentedAttribute[str],
    ) -> ColumnElement[bool]:
        return exists().where(KnowledgeItemFileModel.file_id == file_id)

    async def create_file(self, namespace: Namespace, file: StoredFile) -> StoredFile:
        if file.namespace != namespace:
            raise NamespaceNotAllowedError(namespace=file.namespace)
        file_model = FileModel.from_domain_schema(file)
        self.session.add(file_model)
        await self.session.flush()
        return file_model.to_domain_schema()

    async def get_file(self, namespace: Namespace, file_id: str) -> StoredFile:
        file_model = await self.session.scalar(
            select(FileModel).where(
                FileModel.namespace == namespace,
                FileModel.id == file_id,
            ),
        )
        if file_model is None:
            raise EntryNotFoundError
        return file_model.to_domain_schema()

    async def list_files(self, namespace: Namespace, purpose: FilePurpose) -> StoredFiles:
        query = (
            select(FileModel)
            .where(
                FileModel.namespace == namespace,
                FileModel.purpose == purpose,
            )
            .order_by(FileModel.created_at.desc(), FileModel.id)
        )
        file_models = await self.session.scalars(query)
        return StoredFiles(
            values=[file_model.to_domain_schema() for file_model in file_models],
        )

    async def find_file_by_original_sha256(
        self,
        namespace: Namespace,
        purpose: FilePurpose,
        original_sha256: str,
    ) -> StoredFile | None:
        query = (
            select(FileModel)
            .where(
                FileModel.namespace == namespace,
                FileModel.purpose == purpose,
                FileModel.original_sha256 == original_sha256,
            )
            .order_by(FileModel.created_at, FileModel.id)
            .limit(1)
            .with_for_update()
        )
        file_model = await self.session.scalar(query)
        if file_model is None:
            return None
        return file_model.to_domain_schema()

    async def refresh_file_orphaned_at(
        self,
        namespace: Namespace,
        file_id: str,
        orphaned_at: datetime,
    ) -> StoredFile:
        query = (
            update(FileModel)
            .where(
                FileModel.namespace == namespace,
                FileModel.id == file_id,
                FileModel.orphaned_at.is_not(None),
            )
            .values(orphaned_at=orphaned_at)
            .returning(FileModel)
        )
        file_model = await self.session.scalar(query)
        if file_model is None:
            return await self.get_file(namespace=namespace, file_id=file_id)
        return file_model.to_domain_schema()

    async def update_file_name(
        self,
        namespace: Namespace,
        file_id: str,
        name: str,
        updated_at: datetime,
    ) -> StoredFile:
        query = (
            update(FileModel)
            .where(
                FileModel.namespace == namespace,
                FileModel.id == file_id,
            )
            .values(name=name, updated_at=updated_at)
            .returning(FileModel)
        )
        file_model = await self.session.scalar(query)
        if file_model is None:
            raise EntryNotFoundError
        return file_model.to_domain_schema()

    async def file_has_usages(self, namespace: Namespace, file_id: str) -> bool:
        return bool(
            await self.session.scalar(
                select(self.file_usage_exists(FileModel.id)).where(
                    FileModel.namespace == namespace,
                    FileModel.id == file_id,
                ),
            ),
        )

    async def lock_files(self, namespace: Namespace, file_ids: frozenset[str]) -> None:
        if not file_ids:
            return
        query = (
            select(FileModel.id)
            .where(
                FileModel.namespace == namespace,
                FileModel.id.in_(file_ids),
            )
            .order_by(FileModel.id)
            .with_for_update()
        )
        tuple(await self.session.scalars(query))

    async def set_files_attached(
        self,
        namespace: Namespace,
        file_ids: frozenset[str],
    ) -> None:
        if not file_ids:
            return
        await self.lock_files(namespace=namespace, file_ids=file_ids)
        await self.session.execute(
            update(FileModel)
            .where(
                FileModel.namespace == namespace,
                FileModel.id.in_(file_ids),
                FileModel.orphaned_at.is_not(None),
            )
            .values(orphaned_at=None),
        )

    async def set_files_orphaned_if_unused(
        self,
        namespace: Namespace,
        file_ids: frozenset[str],
        orphaned_at: datetime,
    ) -> None:
        if not file_ids:
            return
        await self.lock_files(namespace=namespace, file_ids=file_ids)
        await self.session.execute(
            update(FileModel)
            .where(
                FileModel.namespace == namespace,
                FileModel.id.in_(file_ids),
                ~self.file_usage_exists(FileModel.id),
            )
            .values(orphaned_at=orphaned_at),
        )

    async def list_orphaned_files_for_cleanup(
        self,
        namespace: Namespace,
        cutoff: datetime,
        limit: int,
    ) -> StoredFiles:
        query = (
            select(FileModel)
            .where(
                FileModel.namespace == namespace,
                FileModel.orphaned_at.is_not(None),
                FileModel.orphaned_at < cutoff,
            )
            .order_by(FileModel.orphaned_at, FileModel.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        file_models = await self.session.scalars(query)
        return StoredFiles(
            values=[file_model.to_domain_schema() for file_model in file_models],
        )

    async def delete_file(self, namespace: Namespace, file_id: str) -> None:
        await self.session.execute(
            delete(FileModel).where(
                FileModel.namespace == namespace,
                FileModel.id == file_id,
            ),
        )
