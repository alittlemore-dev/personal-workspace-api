from dataclasses import dataclass
from datetime import datetime

from core.knowledge.exceptions import (
    InvalidKnowledgeDataError,
    KnowledgeFileNotFoundError,
)
from core.knowledge.files.clients import KnowledgeFileRollbackRegistrar
from core.knowledge.files.enums import KnowledgeFileKind, KnowledgeFileProcessing
from core.knowledge.files.schemas import (
    KnowledgeFile,
    KnowledgeFileContent,
    KnowledgeFileMutationResult,
    KnowledgeFileUpdateParams,
    KnowledgeFileUploadParams,
)
from core.knowledge.files.services import KnowledgeFileCrudService
from core.knowledge.files.storages import KnowledgeFilesStorage
from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.items.storages import KnowledgeItemsStorage


@dataclass(kw_only=True, slots=True, frozen=True)
class KnowledgeFilesUseCase:
    item_storage: KnowledgeItemsStorage
    file_storage: KnowledgeFilesStorage
    file_service: KnowledgeFileCrudService

    async def upload_attachment(
        self,
        *,
        params: KnowledgeFileUploadParams,
        processing: KnowledgeFileProcessing,
        rollback_registrar: KnowledgeFileRollbackRegistrar,
        current_datetime: datetime,
    ) -> KnowledgeFile:
        item = await self.item_storage.get_item_for_author(
            item_id=params.item_id,
            author_username=params.author_username,
        )
        if params.kind != KnowledgeFileKind.ATTACHMENT:
            raise InvalidKnowledgeDataError
        file = await self.file_service.create_file(
            params=params,
            processing=processing,
            now=current_datetime,
            rollback_registrar=rollback_registrar,
        )
        await self.item_storage.touch_items(
            item_ids={item.id},
            author_username=item.author_username,
            kind=item.kind,
            updated_at=current_datetime,
        )
        return file

    async def replace_person_photo(
        self,
        *,
        params: KnowledgeFileUploadParams,
        rollback_registrar: KnowledgeFileRollbackRegistrar,
        current_datetime: datetime,
    ) -> KnowledgeFileMutationResult:
        item = await self.item_storage.get_item(
            item_id=params.item_id,
            author_username=params.author_username,
            kind=KnowledgeItemKind.PERSON,
        )
        if params.kind != KnowledgeFileKind.PERSON_PHOTO:
            raise InvalidKnowledgeDataError
        existing_files = await self.file_storage.list_item_files(
            item_id=item.id,
            author_username=item.author_username,
        )
        existing_photo = next(
            (file for file in existing_files if file.kind == KnowledgeFileKind.PERSON_PHOTO),
            None,
        )
        object_names_to_delete: tuple[str, ...] = ()
        if existing_photo is not None:
            deleted = await self.file_service.delete_file(file=existing_photo)
            if deleted is not None:
                object_names_to_delete = (deleted.relative_path,)
        file = await self.file_service.create_file(
            params=params,
            processing=KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE,
            now=current_datetime,
            rollback_registrar=rollback_registrar,
        )
        await self.item_storage.touch_items(
            item_ids={item.id},
            author_username=item.author_username,
            kind=item.kind,
            updated_at=current_datetime,
        )
        return KnowledgeFileMutationResult(
            file=file,
            object_names_to_delete=object_names_to_delete,
        )

    async def rename_attachment(
        self,
        *,
        item_id: str,
        file_id: str,
        author_username: str,
        params: KnowledgeFileUpdateParams,
        current_datetime: datetime,
    ) -> KnowledgeFile:
        item = await self.item_storage.get_item_for_author(
            item_id=item_id,
            author_username=author_username,
        )
        file = await self.file_storage.get_file(
            file_id=file_id,
            author_username=author_username,
        )
        if file.item_id != item.id or file.kind != KnowledgeFileKind.ATTACHMENT:
            raise KnowledgeFileNotFoundError
        file = await self.file_service.rename_file(
            file=file,
            params=params,
            updated_at=current_datetime,
        )
        await self.item_storage.touch_items(
            item_ids={item.id},
            author_username=item.author_username,
            kind=item.kind,
            updated_at=current_datetime,
        )
        return file

    async def delete_attachment(
        self,
        *,
        item_id: str,
        file_id: str,
        author_username: str,
        current_datetime: datetime,
    ) -> KnowledgeFileMutationResult:
        item = await self.item_storage.get_item_for_author(
            item_id=item_id,
            author_username=author_username,
        )
        file = await self.file_storage.get_file(
            file_id=file_id,
            author_username=author_username,
        )
        if file.item_id != item.id or file.kind != KnowledgeFileKind.ATTACHMENT:
            raise KnowledgeFileNotFoundError
        deleted = await self.file_service.delete_file(file=file)
        await self.item_storage.touch_items(
            item_ids={item.id},
            author_username=item.author_username,
            kind=item.kind,
            updated_at=current_datetime,
        )
        return KnowledgeFileMutationResult(
            file=None,
            object_names_to_delete=((deleted.relative_path,) if deleted is not None else ()),
        )

    async def delete_person_photo(
        self,
        *,
        person_id: str,
        author_username: str,
        current_datetime: datetime,
    ) -> KnowledgeFileMutationResult:
        item = await self.item_storage.get_item(
            item_id=person_id,
            author_username=author_username,
            kind=KnowledgeItemKind.PERSON,
        )
        files = await self.file_storage.list_item_files(
            item_id=person_id,
            author_username=author_username,
        )
        photo = next(
            (file for file in files if file.kind == KnowledgeFileKind.PERSON_PHOTO),
            None,
        )
        if photo is None:
            raise KnowledgeFileNotFoundError
        deleted = await self.file_service.delete_file(file=photo)
        await self.item_storage.touch_items(
            item_ids={item.id},
            author_username=item.author_username,
            kind=item.kind,
            updated_at=current_datetime,
        )
        return KnowledgeFileMutationResult(
            file=None,
            object_names_to_delete=((deleted.relative_path,) if deleted is not None else ()),
        )

    async def get_file_content(
        self,
        *,
        file_id: str,
        author_username: str,
    ) -> KnowledgeFileContent:
        return await self.file_service.read_file(
            file_id=file_id,
            author_username=author_username,
        )
