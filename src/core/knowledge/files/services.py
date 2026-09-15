import hashlib
from dataclasses import dataclass
from datetime import datetime

from core.files.exceptions import FileSizeTooLargeError
from core.files.file_name_generators import FileNameGenerator
from core.files.storages import FileStorage
from core.knowledge.files.clients import (
    KnowledgeFileClient,
    KnowledgeFileRollbackRegistrar,
    KnowledgePhotoProcessor,
)
from core.knowledge.files.enums import KnowledgeFileProcessing
from core.knowledge.files.schemas import (
    KnowledgeFile,
    KnowledgeFileContent,
    KnowledgeFileServiceConfig,
    KnowledgeFileUpdateParams,
    KnowledgeFileUploadParams,
)
from core.knowledge.files.storages import KnowledgeFilesStorage


@dataclass(kw_only=True, slots=True, frozen=True)
class KnowledgeFileCrudService:
    storage: KnowledgeFilesStorage
    shared_file_storage: FileStorage
    client: KnowledgeFileClient
    photo_processor: KnowledgePhotoProcessor
    file_name_generator: FileNameGenerator
    config: KnowledgeFileServiceConfig

    async def create_file(
        self,
        *,
        params: KnowledgeFileUploadParams,
        processing: KnowledgeFileProcessing,
        now: datetime,
        rollback_registrar: KnowledgeFileRollbackRegistrar,
    ) -> KnowledgeFile:
        rules = (
            self.config.normalized_raster_image_rules
            if processing == KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE
            else self.config.rules
        )
        rule = rules.require(kind=params.kind)
        params.validate(rule=rule)
        content = params.content
        mime_type = params.mime_type
        if processing == KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE:
            processed = self.photo_processor.process(params=params)
            content = processed.content
            mime_type = processed.mime_type
            if len(content) > rule.max_size_bytes:
                raise FileSizeTooLargeError(
                    size_bytes=len(content),
                    max_size_bytes=rule.max_size_bytes,
                )
        relative_path = self.file_name_generator(
            folder=rule.folder,
            file_extension=(
                ".webp"
                if processing == KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE
                else params.file_extension
            ),
        )
        file = KnowledgeFile(
            id=params.id,
            item_id=params.item_id,
            author_username=params.author_username,
            kind=params.kind,
            processing=processing,
            relative_path=relative_path,
            mime_type=mime_type,
            size_bytes=len(content),
            name=params.name.strip(),
            original_name=params.original_name,
            original_sha256=hashlib.sha256(params.content).hexdigest(),
            created_at=now,
            updated_at=now,
        )
        file = await self.storage.create_file(file=file)
        await self.client.upload_file(
            content=content,
            object_name=file.relative_path,
            content_type=file.mime_type,
        )
        rollback_registrar.register_new_object(object_name=file.relative_path)
        return file

    async def read_file(self, *, file_id: str, author_username: str) -> KnowledgeFileContent:
        file = await self.storage.get_file(
            file_id=file_id,
            author_username=author_username,
        )
        return KnowledgeFileContent(
            file=file,
            content=self.client.stream_file(object_name=file.relative_path),
        )

    async def rename_file(
        self,
        *,
        file: KnowledgeFile,
        params: KnowledgeFileUpdateParams,
        updated_at: datetime,
    ) -> KnowledgeFile:
        params.validate()
        return await self.storage.update_file_name(
            file=file,
            name=params.name.strip(),
            updated_at=updated_at,
        )

    async def delete_file(self, *, file: KnowledgeFile) -> KnowledgeFile | None:
        await self.shared_file_storage.lock_files(
            namespace=self.config.namespace,
            file_ids=frozenset({file.id}),
        )
        await self.storage.delete_file(file=file)
        if await self.shared_file_storage.file_has_usages(
            namespace=self.config.namespace,
            file_id=file.id,
        ):
            return None
        await self.shared_file_storage.delete_file(
            namespace=self.config.namespace,
            file_id=file.id,
        )
        return file

    async def delete_files(self, *, files: list[KnowledgeFile]) -> tuple[str, ...]:
        object_names: list[str] = []
        for file in files:
            deleted = await self.delete_file(file=file)
            if deleted is not None:
                object_names.append(deleted.relative_path)
        return tuple(object_names)
