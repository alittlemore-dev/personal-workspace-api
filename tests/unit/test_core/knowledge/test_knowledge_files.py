from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import Mock, call

import pytest

from core.files.exceptions import (
    ContentTypeNotAllowedError,
    FileImageOptimizationError,
    FileNameInvalidError,
    FileSizeTooLargeError,
    InvalidFileDataError,
)
from core.files.storages import FileStorage
from core.knowledge.exceptions import KnowledgeFileNotFoundError
from core.knowledge.files.clients import (
    KnowledgeFileClient,
    KnowledgeFileRollbackRegistrar,
    KnowledgePhotoProcessor,
)
from core.knowledge.files.enums import KnowledgeFileKind, KnowledgeFileProcessing
from core.knowledge.files.schemas import (
    KnowledgeFile,
    KnowledgeFileMutationResult,
    KnowledgeFileRule,
    KnowledgeFileRules,
    KnowledgeFileServiceConfig,
    KnowledgeFileUpdateParams,
    KnowledgeFileUploadParams,
    ProcessedKnowledgePhoto,
)
from core.knowledge.files.services import KnowledgeFileCrudService
from core.knowledge.files.storages import KnowledgeFilesStorage
from core.knowledge.files.use_cases import KnowledgeFilesUseCase
from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.items.schemas import KnowledgeItem
from core.knowledge.items.storages import KnowledgeItemsStorage
from tests.test_cases import TestCase

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


class TestKnowledgeFileCrudService(TestCase):
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.storage = Mock(spec=KnowledgeFilesStorage)
        self.shared_file_storage = Mock(spec=FileStorage)
        self.client = Mock(spec=KnowledgeFileClient)
        self.photo_processor = Mock(spec=KnowledgePhotoProcessor)
        self.rollback_registrar = Mock(spec=KnowledgeFileRollbackRegistrar)
        self.file_name_generator = Mock(return_value="attachments/object.bin")
        self.rules = KnowledgeFileRules(
            values={
                KnowledgeFileKind.ATTACHMENT: KnowledgeFileRule(
                    folder="attachments",
                    allowed_mime_types=frozenset({"*/*"}),
                    max_size_bytes=20,
                    original_name_max_length=255,
                    mime_type_max_length=255,
                ),
                KnowledgeFileKind.PERSON_PHOTO: KnowledgeFileRule(
                    folder="person-photos",
                    allowed_mime_types=frozenset(
                        {"image/jpeg", "image/png", "image/webp"},
                    ),
                    max_size_bytes=5,
                    original_name_max_length=255,
                    mime_type_max_length=255,
                ),
            },
        )
        self.normalized_raster_image_rules = KnowledgeFileRules(
            values={
                KnowledgeFileKind.ATTACHMENT: KnowledgeFileRule(
                    folder="editor-images",
                    allowed_mime_types=frozenset(
                        {"image/jpeg", "image/png", "image/webp"},
                    ),
                    max_size_bytes=5,
                    original_name_max_length=255,
                    mime_type_max_length=255,
                ),
                KnowledgeFileKind.PERSON_PHOTO: KnowledgeFileRule(
                    folder="person-photos",
                    allowed_mime_types=frozenset(
                        {"image/jpeg", "image/png", "image/webp"},
                    ),
                    max_size_bytes=5,
                    original_name_max_length=255,
                    mime_type_max_length=255,
                ),
            },
        )
        self.service = KnowledgeFileCrudService(
            storage=self.storage,
            shared_file_storage=self.shared_file_storage,
            client=self.client,
            photo_processor=self.photo_processor,
            file_name_generator=self.file_name_generator,
            config=KnowledgeFileServiceConfig(
                namespace="knowledge-private",
                rules=self.rules,
                normalized_raster_image_rules=self.normalized_raster_image_rules,
            ),
        )

    async def test_delete_unlinks_and_deletes_unused_shared_metadata(self) -> None:
        file = KnowledgeFile(
            id="1" * 32,
            item_id="2" * 32,
            author_username="owner",
            kind=KnowledgeFileKind.ATTACHMENT,
            processing=KnowledgeFileProcessing.RAW,
            relative_path="attachments/private.bin",
            mime_type="application/octet-stream",
            size_bytes=7,
            name="Private",
            original_name="private.bin",
            original_sha256="a" * 64,
            created_at=NOW,
            updated_at=NOW,
        )
        self.shared_file_storage.file_has_usages.return_value = False

        deleted = await self.service.delete_file(file=file)

        assert deleted == file
        self.shared_file_storage.lock_files.assert_awaited_once_with(
            namespace="knowledge-private",
            file_ids=frozenset({file.id}),
        )
        self.storage.delete_file.assert_awaited_once_with(file=file)
        self.shared_file_storage.file_has_usages.assert_awaited_once_with(
            namespace="knowledge-private",
            file_id=file.id,
        )
        self.shared_file_storage.delete_file.assert_awaited_once_with(
            namespace="knowledge-private",
            file_id=file.id,
        )

    async def test_delete_keeps_shared_metadata_when_usage_remains(self) -> None:
        file = KnowledgeFile(
            id="1" * 32,
            item_id="2" * 32,
            author_username="owner",
            kind=KnowledgeFileKind.ATTACHMENT,
            processing=KnowledgeFileProcessing.RAW,
            relative_path="attachments/private.bin",
            mime_type="application/octet-stream",
            size_bytes=7,
            name="Private",
            original_name="private.bin",
            original_sha256="a" * 64,
            created_at=NOW,
            updated_at=NOW,
        )
        self.shared_file_storage.file_has_usages.return_value = True

        deleted = await self.service.delete_file(file=file)

        assert deleted is None
        self.shared_file_storage.lock_files.assert_awaited_once_with(
            namespace="knowledge-private",
            file_ids=frozenset({file.id}),
        )
        self.storage.delete_file.assert_awaited_once_with(file=file)
        self.shared_file_storage.file_has_usages.assert_awaited_once_with(
            namespace="knowledge-private",
            file_id=file.id,
        )
        self.shared_file_storage.delete_file.assert_not_awaited()

    async def test_delete_locks_metadata_before_unlinking_usage(self) -> None:
        file = KnowledgeFile(
            id="1" * 32,
            item_id="2" * 32,
            author_username="owner",
            kind=KnowledgeFileKind.ATTACHMENT,
            processing=KnowledgeFileProcessing.RAW,
            relative_path="attachments/private.bin",
            mime_type="application/octet-stream",
            size_bytes=7,
            name="Private",
            original_name="private.bin",
            original_sha256="a" * 64,
            created_at=NOW,
            updated_at=NOW,
        )
        self.shared_file_storage.file_has_usages.return_value = False
        operations = Mock()
        operations.attach_mock(self.shared_file_storage.lock_files, "lock_metadata")
        operations.attach_mock(self.storage.delete_file, "unlink_usage")

        await self.service.delete_file(file=file)

        assert operations.mock_calls[:2] == [
            call.lock_metadata(
                namespace="knowledge-private",
                file_ids=frozenset({file.id}),
            ),
            call.unlink_usage(file=file),
        ]

    async def test_delete_files_returns_only_paths_safe_for_object_cleanup(self) -> None:
        deleted_file = KnowledgeFile(
            id="1" * 32,
            item_id="3" * 32,
            author_username="owner",
            kind=KnowledgeFileKind.ATTACHMENT,
            processing=KnowledgeFileProcessing.RAW,
            relative_path="attachments/deleted.bin",
            mime_type="application/octet-stream",
            size_bytes=7,
            name="Deleted",
            original_name="deleted.bin",
            original_sha256="a" * 64,
            created_at=NOW,
            updated_at=NOW,
        )
        shared_file = replace(
            deleted_file,
            id="2" * 32,
            relative_path="attachments/shared.bin",
        )
        self.shared_file_storage.file_has_usages.side_effect = [False, True]

        paths = await self.service.delete_files(files=[deleted_file, shared_file])

        assert paths == ("attachments/deleted.bin",)

    async def test_attachment_upload_persists_private_metadata_and_object(self) -> None:
        params = KnowledgeFileUploadParams(
            id="1" * 32,
            item_id="2" * 32,
            author_username="owner",
            kind=KnowledgeFileKind.ATTACHMENT,
            name=" Notes ",
            original_name="notes.txt",
            mime_type="text/plain",
            content=b"private",
        )
        self.storage.create_file.side_effect = lambda *, file: file

        result = await self.service.create_file(
            params=params,
            processing=KnowledgeFileProcessing.RAW,
            now=NOW,
            rollback_registrar=self.rollback_registrar,
        )

        assert result.name == "Notes"
        assert result.original_sha256
        assert result.relative_path == "attachments/object.bin"
        self.photo_processor.process.assert_not_called()
        self.client.upload_file.assert_awaited_once()
        self.rollback_registrar.register_new_object.assert_called_once_with(
            object_name="attachments/object.bin",
        )

    async def test_photo_upload_always_uses_processed_webp(self) -> None:
        params = KnowledgeFileUploadParams(
            id="1" * 32,
            item_id="2" * 32,
            author_username="owner",
            kind=KnowledgeFileKind.PERSON_PHOTO,
            name="Photo",
            original_name="photo.png",
            mime_type="image/png",
            content=b"png",
        )
        self.photo_processor.process.return_value = ProcessedKnowledgePhoto(
            content=b"webp",
            mime_type="image/webp",
        )
        self.storage.create_file.side_effect = lambda *, file: file

        result = await self.service.create_file(
            params=params,
            processing=KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE,
            now=NOW,
            rollback_registrar=self.rollback_registrar,
        )

        assert result.mime_type == "image/webp"
        self.client.upload_file.assert_awaited_once()
        self.rollback_registrar.register_new_object.assert_called_once_with(
            object_name="attachments/object.bin",
        )

    async def test_editor_image_upload_normalizes_attachment_into_dedicated_folder(self) -> None:
        params = KnowledgeFileUploadParams(
            id="1" * 32,
            item_id="2" * 32,
            author_username="owner",
            kind=KnowledgeFileKind.ATTACHMENT,
            name="diagram.png",
            original_name="diagram.png",
            mime_type="image/png",
            content=b"png",
        )
        self.photo_processor.process.return_value = ProcessedKnowledgePhoto(
            content=b"webp",
            mime_type="image/webp",
        )
        self.file_name_generator.return_value = "editor-images/object.webp"
        self.storage.create_file.side_effect = lambda *, file: file

        result = await self.service.create_file(
            params=params,
            processing=KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE,
            now=NOW,
            rollback_registrar=self.rollback_registrar,
        )

        assert result.kind == KnowledgeFileKind.ATTACHMENT
        assert result.processing == KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE
        assert result.relative_path == "editor-images/object.webp"
        assert result.mime_type == "image/webp"
        assert result.size_bytes == len(b"webp")
        self.photo_processor.process.assert_called_once_with(params=params)
        self.file_name_generator.assert_called_once_with(
            folder="editor-images",
            file_extension=".webp",
        )
        self.storage.create_file.assert_awaited_once_with(file=result)
        self.rollback_registrar.register_new_object.assert_called_once_with(
            object_name="editor-images/object.webp",
        )

    async def test_editor_image_upload_rejects_invalid_decoded_image_before_persistence(
        self,
    ) -> None:
        params = KnowledgeFileUploadParams(
            id="1" * 32,
            item_id="2" * 32,
            author_username="owner",
            kind=KnowledgeFileKind.ATTACHMENT,
            name="diagram.png",
            original_name="diagram.png",
            mime_type="image/png",
            content=b"bad",
        )
        self.photo_processor.process.side_effect = FileImageOptimizationError

        with pytest.raises(FileImageOptimizationError):
            await self.service.create_file(
                params=params,
                processing=KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE,
                now=NOW,
                rollback_registrar=self.rollback_registrar,
            )

        self.storage.create_file.assert_not_awaited()
        self.client.upload_file.assert_not_awaited()
        self.rollback_registrar.register_new_object.assert_not_called()

    @pytest.mark.parametrize(
        ("params", "error"),
        [
            (
                KnowledgeFileUploadParams(
                    id="1" * 32,
                    item_id="2" * 32,
                    author_username="owner",
                    kind=KnowledgeFileKind.ATTACHMENT,
                    name=" ",
                    original_name="file.txt",
                    mime_type="text/plain",
                    content=b"x",
                ),
                FileNameInvalidError,
            ),
            (
                KnowledgeFileUploadParams(
                    id="1" * 32,
                    item_id="2" * 32,
                    author_username="owner",
                    kind=KnowledgeFileKind.PERSON_PHOTO,
                    name="Photo",
                    original_name="file.gif",
                    mime_type="image/gif",
                    content=b"x",
                ),
                ContentTypeNotAllowedError,
            ),
            (
                KnowledgeFileUploadParams(
                    id="1" * 32,
                    item_id="2" * 32,
                    author_username="owner",
                    kind=KnowledgeFileKind.PERSON_PHOTO,
                    name="Photo",
                    original_name="file.png",
                    mime_type="image/png",
                    content=b"123456",
                ),
                FileSizeTooLargeError,
            ),
            (
                KnowledgeFileUploadParams(
                    id="1" * 32,
                    item_id="2" * 32,
                    author_username="owner",
                    kind=KnowledgeFileKind.ATTACHMENT,
                    name="File",
                    original_name="x" * 256,
                    mime_type="text/plain",
                    content=b"x",
                ),
                FileNameInvalidError,
            ),
            (
                KnowledgeFileUploadParams(
                    id="1" * 32,
                    item_id="2" * 32,
                    author_username="owner",
                    kind=KnowledgeFileKind.ATTACHMENT,
                    name="File",
                    original_name="file.txt",
                    mime_type="x" * 256,
                    content=b"x",
                ),
                InvalidFileDataError,
            ),
        ],
    )
    async def test_upload_rejects_invalid_input(
        self,
        params: KnowledgeFileUploadParams,
        error: type[Exception],
    ) -> None:
        with pytest.raises(error):
            await self.service.create_file(
                params=params,
                processing=(
                    KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE
                    if params.kind == KnowledgeFileKind.PERSON_PHOTO
                    else KnowledgeFileProcessing.RAW
                ),
                now=NOW,
                rollback_registrar=self.rollback_registrar,
            )


class TestKnowledgeFilesUseCase(TestCase):
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.item_storage = Mock(spec=KnowledgeItemsStorage)
        self.file_storage = Mock(spec=KnowledgeFilesStorage)
        self.file_service = Mock(spec=KnowledgeFileCrudService)
        self.use_case = KnowledgeFilesUseCase(
            item_storage=self.item_storage,
            file_storage=self.file_storage,
            file_service=self.file_service,
        )
        self.item = KnowledgeItem(
            id="1" * 32,
            kind=KnowledgeItemKind.PERSON,
            author_username="owner",
            display_name="Person",
            description="",
            tags=[],
            created_at=NOW,
            updated_at=NOW,
        )
        self.file = KnowledgeFile(
            id="2" * 32,
            item_id=self.item.id,
            author_username="owner",
            kind=KnowledgeFileKind.ATTACHMENT,
            processing=KnowledgeFileProcessing.RAW,
            relative_path="attachments/private.bin",
            mime_type="application/octet-stream",
            size_bytes=7,
            name="Private",
            original_name="private.bin",
            original_sha256="a" * 64,
            created_at=NOW,
            updated_at=NOW,
        )

    async def test_rename_rejects_foreign_nested_file_as_not_found(self) -> None:
        self.item_storage.get_item_for_author.return_value = self.item
        self.file_storage.get_file.return_value = replace(self.file, item_id="3" * 32)

        with pytest.raises(KnowledgeFileNotFoundError):
            await self.use_case.rename_attachment(
                item_id=self.item.id,
                file_id=self.file.id,
                author_username="owner",
                params=KnowledgeFileUpdateParams(name="Renamed"),
                current_datetime=NOW,
            )

    async def test_delete_attachment_returns_post_commit_cleanup_path(self) -> None:
        self.item_storage.get_item_for_author.return_value = self.item
        self.file_storage.get_file.return_value = self.file
        self.file_service.delete_file.return_value = self.file

        result = await self.use_case.delete_attachment(
            item_id=self.item.id,
            file_id=self.file.id,
            author_username="owner",
            current_datetime=NOW,
        )

        assert result == KnowledgeFileMutationResult(
            file=None,
            object_names_to_delete=("attachments/private.bin",),
        )
        self.item_storage.touch_items.assert_awaited_once()
        assert self.item_storage.touch_items.await_args.kwargs["updated_at"] == NOW

    async def test_delete_attachment_omits_cleanup_path_when_shared_usage_remains(self) -> None:
        self.item_storage.get_item_for_author.return_value = self.item
        self.file_storage.get_file.return_value = self.file
        self.file_service.delete_file.return_value = None

        result = await self.use_case.delete_attachment(
            item_id=self.item.id,
            file_id=self.file.id,
            author_username="owner",
            current_datetime=NOW,
        )

        assert result == KnowledgeFileMutationResult(
            file=None,
            object_names_to_delete=(),
        )

    async def test_attachment_upload_reuses_supplied_datetime_for_file_and_item(self) -> None:
        self.item_storage.get_item_for_author.return_value = self.item
        params = KnowledgeFileUploadParams(
            id="3" * 32,
            item_id=self.item.id,
            author_username="owner",
            kind=KnowledgeFileKind.ATTACHMENT,
            name="Private",
            original_name="private.bin",
            mime_type="application/octet-stream",
            content=b"private",
        )
        self.file_service.create_file.return_value = self.file
        rollback_registrar = Mock(spec=KnowledgeFileRollbackRegistrar)

        result = await self.use_case.upload_attachment(
            params=params,
            processing=KnowledgeFileProcessing.RAW,
            rollback_registrar=rollback_registrar,
            current_datetime=NOW,
        )

        assert result == self.file
        assert self.file_service.create_file.await_args.kwargs["now"] == NOW
        assert (
            self.file_service.create_file.await_args.kwargs["processing"]
            == KnowledgeFileProcessing.RAW
        )
        assert self.item_storage.touch_items.await_args.kwargs["updated_at"] == NOW

    async def test_editor_image_upload_keeps_attachment_kind_without_photo_singleton_lookup(
        self,
    ) -> None:
        self.item_storage.get_item_for_author.return_value = self.item
        params = KnowledgeFileUploadParams(
            id="3" * 32,
            item_id=self.item.id,
            author_username="owner",
            kind=KnowledgeFileKind.ATTACHMENT,
            name="diagram.png",
            original_name="diagram.png",
            mime_type="image/png",
            content=b"png",
        )
        normalized_file = replace(
            self.file,
            relative_path="editor-images/private.webp",
            mime_type="image/webp",
            original_name="diagram.png",
        )
        self.file_service.create_file.return_value = normalized_file
        rollback_registrar = Mock(spec=KnowledgeFileRollbackRegistrar)

        result = await self.use_case.upload_attachment(
            params=params,
            processing=KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE,
            rollback_registrar=rollback_registrar,
            current_datetime=NOW,
        )

        assert result.kind == KnowledgeFileKind.ATTACHMENT
        assert result.mime_type == "image/webp"
        self.file_service.create_file.assert_awaited_once_with(
            params=params,
            processing=KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE,
            now=NOW,
            rollback_registrar=rollback_registrar,
        )
        self.file_storage.list_item_files.assert_not_awaited()
