import hashlib
from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import Mock

import pytest

from core.files.clients import FileClient
from core.files.enums import FilePurpose
from core.files.exceptions import (
    ContentTypeNotAllowedError,
    FileInUseError,
    FileNameInvalidError,
    FilePurposeNotAllowedError,
    FileSizeTooLargeError,
)
from core.files.file_name_generators import FileNameGenerator
from core.files.processors import FileContentProcessor
from core.files.schemas import (
    FileRead,
    FileRule,
    FileRules,
    FileServiceConfig,
    FileUpdateParams,
    FileUploadParams,
    StoredFile,
)
from core.files.services import FileService
from core.files.storages import FileStorage
from core.files.types import Namespace

NOW = datetime(2026, 7, 3, 10, 0, tzinfo=UTC)
NAMESPACE: Namespace = "media"


def stored_file(
    *,
    file_id: str = "file-id",
    purpose: FilePurpose = FilePurpose.ATTACHMENT,
    orphaned_at: datetime | None = NOW,
) -> StoredFile:
    return StoredFile(
        id=file_id,
        purpose=purpose,
        namespace=NAMESPACE,
        relative_path=f"attachments/{file_id}.pdf",
        mime_type="application/pdf",
        size_bytes=4,
        name="Attachment",
        original_name="original.pdf",
        original_sha256=hashlib.sha256(b"data").hexdigest(),
        orphaned_at=orphaned_at,
        created_at=NOW,
        updated_at=NOW,
    )


class TestFileService:
    def setup_method(self) -> None:
        self.file_client = Mock(spec=FileClient)
        self.file_storage = Mock(spec=FileStorage)
        self.file_name_generator = Mock(spec=FileNameGenerator)
        self.file_name_generator.return_value = "attachments/file-id.pdf"
        self.processor = Mock(spec=FileContentProcessor)
        self.processor.process.side_effect = lambda *, params: params
        self.file_storage.find_file_by_original_sha256.return_value = None
        self.file_client.get_access_url.return_value = (
            "https://cdn.example.test/media/attachments/file-id.pdf"
        )
        self.service = FileService(
            file_client=self.file_client,
            file_storage=self.file_storage,
            file_name_generator=self.file_name_generator,
            file_content_processor=self.processor,
            config=FileServiceConfig(
                namespace=NAMESPACE,
                rules=FileRules(
                    values={
                        FilePurpose.ATTACHMENT: FileRule(
                            folder="attachments",
                            allowed_mime_types=frozenset({"application/pdf"}),
                            max_size_bytes=4,
                        ),
                    },
                ),
            ),
        )

    async def test_upload_validates_processes_and_persists_namespaced_metadata(self) -> None:
        persisted = stored_file()
        self.file_storage.create_file.return_value = persisted

        result = await self.service.upload_file(
            params=FileUploadParams(
                id="file-id",
                purpose=FilePurpose.ATTACHMENT,
                name="Attachment",
                original_name="original.pdf",
                mime_type="application/pdf",
                content=b"data",
            ),
            current_datetime=NOW,
        )

        assert result == FileRead(
            file=persisted,
            access_url="https://cdn.example.test/media/attachments/file-id.pdf",
            markdown_url=("https://cdn.example.test/media/attachments/file-id.pdf#fileId=file-id"),
        )
        self.file_storage.create_file.assert_awaited_once_with(
            namespace=NAMESPACE,
            file=persisted,
        )
        upload = self.file_client.upload_file.await_args.kwargs
        assert isinstance(upload["file_data"], BytesIO)
        assert upload["file_data"].getvalue() == b"data"
        assert upload["namespace"] == NAMESPACE

    @pytest.mark.parametrize(
        ("name", "mime_type", "content", "error"),
        [
            ("   ", "application/pdf", b"data", FileNameInvalidError),
            ("Attachment", "text/plain", b"data", ContentTypeNotAllowedError),
            ("Attachment", "application/pdf", b"large", FileSizeTooLargeError),
        ],
    )
    async def test_upload_rejects_invalid_current_attachment(
        self,
        name: str,
        mime_type: str,
        content: bytes,
        error: type[Exception],
    ) -> None:
        with pytest.raises(error):
            await self.service.upload_file(
                params=FileUploadParams(
                    id="file-id",
                    purpose=FilePurpose.ATTACHMENT,
                    name=name,
                    original_name="original.pdf",
                    mime_type=mime_type,
                    content=content,
                ),
                current_datetime=NOW,
            )

        self.file_client.upload_file.assert_not_awaited()

    async def test_duplicate_upload_refreshes_orphan_marker_without_object_write(self) -> None:
        duplicate = stored_file(file_id="existing-id")
        refreshed = stored_file(file_id="existing-id", orphaned_at=NOW)
        self.file_storage.find_file_by_original_sha256.return_value = duplicate
        self.file_storage.refresh_file_orphaned_at.return_value = refreshed

        result = await self.service.upload_file(
            params=FileUploadParams(
                id="new-id",
                purpose=FilePurpose.ATTACHMENT,
                name="Attachment",
                original_name="duplicate.pdf",
                mime_type="application/pdf",
                content=b"data",
            ),
            current_datetime=NOW,
        )

        assert result.file == refreshed
        self.file_storage.refresh_file_orphaned_at.assert_awaited_once_with(
            namespace=NAMESPACE,
            file_id="existing-id",
            orphaned_at=NOW,
        )
        self.file_client.upload_file.assert_not_awaited()

    async def test_ensure_files_allowed_rejects_wrong_purpose(self) -> None:
        wrong_purpose = Mock(spec=StoredFile)
        wrong_purpose.purpose = object()
        self.file_storage.get_file.return_value = wrong_purpose

        with pytest.raises(FilePurposeNotAllowedError):
            await self.service.ensure_files_allowed(
                file_ids=frozenset({"file-id"}),
                purpose=FilePurpose.ATTACHMENT,
            )

        self.file_storage.get_file.assert_awaited_once_with(
            namespace=NAMESPACE,
            file_id="file-id",
        )

    async def test_delete_locks_before_checking_usage(self) -> None:
        self.file_storage.file_has_usages.return_value = True

        with pytest.raises(FileInUseError):
            await self.service.delete_file(file_id="file-id")

        self.file_storage.lock_files.assert_awaited_once_with(
            namespace=NAMESPACE,
            file_ids=frozenset({"file-id"}),
        )
        self.file_client.delete_file.assert_not_awaited()

    async def test_update_and_list_preserve_namespace_boundary(self) -> None:
        file = stored_file()
        self.file_storage.update_file_name.return_value = file
        self.file_storage.list_files.return_value = [file]

        updated = await self.service.update_file(
            file_id="file-id",
            params=FileUpdateParams(name="Updated"),
            current_datetime=NOW,
        )
        listed = await self.service.list_files(purpose=FilePurpose.ATTACHMENT)

        assert updated.file == file
        assert listed[0].file == file
        self.file_storage.update_file_name.assert_awaited_once_with(
            namespace=NAMESPACE,
            file_id="file-id",
            name="Updated",
            updated_at=NOW,
        )
        self.file_storage.list_files.assert_awaited_once_with(
            namespace=NAMESPACE,
            purpose=FilePurpose.ATTACHMENT,
        )
