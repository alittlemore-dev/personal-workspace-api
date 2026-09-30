from dataclasses import dataclass

from core.knowledge.exceptions import (
    InvalidKnowledgeDataError,
    KnowledgeFileNotFoundError,
)
from core.knowledge.files.clients import KnowledgeFileRollbackRegistrar
from core.knowledge.files.enums import KnowledgeFileKind, KnowledgeFileProcessing
from core.knowledge.files.schemas import (
    DeleteKnowledgeAttachmentParams,
    DeletePersonPhotoParams,
    KnowledgeFile,
    KnowledgeFileContent,
    KnowledgeFileMutationResult,
    KnowledgeFileTargetParams,
    RenameKnowledgeAttachmentParams,
    ReplacePersonPhotoParams,
    UploadKnowledgeAttachmentParams,
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
    rollback_registrar: KnowledgeFileRollbackRegistrar

    async def upload_attachment(self, *, params: UploadKnowledgeAttachmentParams) -> KnowledgeFile:
        item = await self.item_storage.get_item_for_author(
            item_id=params.data.item_id,
            author_username=params.data.author_username,
        )
        if params.data.kind != KnowledgeFileKind.ATTACHMENT:
            raise InvalidKnowledgeDataError
        file = await self.file_service.create_file(
            params=params.data,
            processing=params.processing,
            now=params.current_datetime,
            rollback_registrar=self.rollback_registrar,
        )
        await self.item_storage.touch_items(
            item_ids={item.id},
            author_username=item.author_username,
            kind=item.kind,
            updated_at=params.current_datetime,
        )
        return file

    async def replace_person_photo(
        self,
        *,
        params: ReplacePersonPhotoParams,
    ) -> KnowledgeFileMutationResult:
        item = await self.item_storage.get_item(
            item_id=params.data.item_id,
            author_username=params.data.author_username,
            kind=KnowledgeItemKind.PERSON,
        )
        if params.data.kind != KnowledgeFileKind.PERSON_PHOTO:
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
            params=params.data,
            processing=KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE,
            now=params.current_datetime,
            rollback_registrar=self.rollback_registrar,
        )
        await self.item_storage.touch_items(
            item_ids={item.id},
            author_username=item.author_username,
            kind=item.kind,
            updated_at=params.current_datetime,
        )
        return KnowledgeFileMutationResult(
            file=file,
            object_names_to_delete=object_names_to_delete,
        )

    async def rename_attachment(self, *, params: RenameKnowledgeAttachmentParams) -> KnowledgeFile:
        item = await self.item_storage.get_item_for_author(
            item_id=params.item_id,
            author_username=params.author_username,
        )
        file = await self.file_storage.get_file(
            file_id=params.file_id,
            author_username=params.author_username,
        )
        if file.item_id != item.id or file.kind != KnowledgeFileKind.ATTACHMENT:
            raise KnowledgeFileNotFoundError
        file = await self.file_service.rename_file(
            file=file,
            params=params.data,
            updated_at=params.current_datetime,
        )
        await self.item_storage.touch_items(
            item_ids={item.id},
            author_username=item.author_username,
            kind=item.kind,
            updated_at=params.current_datetime,
        )
        return file

    async def delete_attachment(
        self,
        *,
        params: DeleteKnowledgeAttachmentParams,
    ) -> KnowledgeFileMutationResult:
        item = await self.item_storage.get_item_for_author(
            item_id=params.item_id,
            author_username=params.author_username,
        )
        file = await self.file_storage.get_file(
            file_id=params.file_id,
            author_username=params.author_username,
        )
        if file.item_id != item.id or file.kind != KnowledgeFileKind.ATTACHMENT:
            raise KnowledgeFileNotFoundError
        deleted = await self.file_service.delete_file(file=file)
        await self.item_storage.touch_items(
            item_ids={item.id},
            author_username=item.author_username,
            kind=item.kind,
            updated_at=params.current_datetime,
        )
        return KnowledgeFileMutationResult(
            file=None,
            object_names_to_delete=((deleted.relative_path,) if deleted is not None else ()),
        )

    async def delete_person_photo(
        self,
        *,
        params: DeletePersonPhotoParams,
    ) -> KnowledgeFileMutationResult:
        item = await self.item_storage.get_item(
            item_id=params.person_id,
            author_username=params.author_username,
            kind=KnowledgeItemKind.PERSON,
        )
        files = await self.file_storage.list_item_files(
            item_id=params.person_id,
            author_username=params.author_username,
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
            updated_at=params.current_datetime,
        )
        return KnowledgeFileMutationResult(
            file=None,
            object_names_to_delete=((deleted.relative_path,) if deleted is not None else ()),
        )

    async def get_file_content(self, *, params: KnowledgeFileTargetParams) -> KnowledgeFileContent:
        return await self.file_service.read_file(
            file_id=params.file_id,
            author_username=params.author_username,
        )
