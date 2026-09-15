from collections.abc import AsyncIterator
from datetime import UTC, datetime
from functools import partial
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import codes

from core.knowledge.exceptions import KnowledgeFileNotFoundError, KnowledgeItemNotFoundError
from core.knowledge.files.enums import KnowledgeFileKind, KnowledgeFileProcessing
from core.knowledge.files.schemas import (
    KnowledgeFile,
    KnowledgeFileContent,
    KnowledgeFileMutationResult,
)
from infra.post_commit_actions import PostCommitActions
from tests.test_cases import ApiTestCase
from tests.unit.conftest import TEST_OWNER_USERNAME

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


async def content_chunks() -> AsyncIterator[bytes]:
    for chunk in (b"private-", b"content"):
        yield chunk


class TestKnowledgeFilesApi(ApiTestCase):
    @pytest_asyncio.fixture(autouse=True)
    async def setup(self) -> None:
        self.use_case = await self.container.get_knowledge_files_use_case()
        self.cleaner = await self.container.get_knowledge_file_object_cleaner()
        self.rollback_registrar = await self.container.get_knowledge_file_rollback_registrar()

    def file(
        self,
        *,
        kind: KnowledgeFileKind,
        processing: KnowledgeFileProcessing = KnowledgeFileProcessing.RAW,
        relative_path: str = "private/object",
        mime_type: str = "text/html",
        original_name: str = 'résumé "<script>.html',
    ) -> KnowledgeFile:
        return KnowledgeFile(
            id="1" * 32,
            item_id="2" * 32,
            author_username="test",
            kind=kind,
            processing=processing,
            relative_path=relative_path,
            mime_type=mime_type,
            size_bytes=15,
            name="Résumé",
            original_name=original_name,
            original_sha256="a" * 64,
            created_at=NOW,
            updated_at=NOW,
        )

    def test_attachment_content_is_author_checked_and_forced_to_download(self) -> None:
        self.use_case.get_file_content.return_value = KnowledgeFileContent(
            file=self.file(kind=KnowledgeFileKind.ATTACHMENT),
            content=content_chunks(),
        )

        response = self.api.client.get(
            "/api/knowledge/files/11111111111111111111111111111111/content",
        )

        self.asserts.status(response=response, expected_status=codes.OK)
        assert response.content == b"private-content"
        assert response.headers["content-type"] == "application/octet-stream"
        assert response.headers["content-disposition"].startswith("attachment;")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cache-control"] == "no-store"
        self.use_case.get_file_content.assert_awaited_once_with(
            file_id="1" * 32,
            author_username=TEST_OWNER_USERNAME,
        )

    def test_photo_content_is_inline_normalized_webp(self) -> None:
        self.use_case.get_file_content.return_value = KnowledgeFileContent(
            file=self.file(
                kind=KnowledgeFileKind.PERSON_PHOTO,
                processing=KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE,
                mime_type="image/webp",
            ),
            content=content_chunks(),
        )

        response = self.api.client.get(
            "/api/knowledge/files/11111111111111111111111111111111/content",
        )

        self.asserts.status(response=response, expected_status=codes.OK)
        assert response.headers["content-type"] == "image/webp"
        assert response.headers["content-disposition"] == 'inline; filename="photo.webp"'

    def test_editor_image_content_is_inline_normalized_webp(self) -> None:
        self.use_case.get_file_content.return_value = KnowledgeFileContent(
            file=self.file(
                kind=KnowledgeFileKind.ATTACHMENT,
                processing=KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE,
                relative_path="editor-images/private.webp",
                mime_type="image/webp",
                original_name="private.png",
            ),
            content=content_chunks(),
        )

        response = self.api.client.get(
            "/api/knowledge/files/11111111111111111111111111111111/content",
        )

        self.asserts.status(response=response, expected_status=codes.OK)
        assert response.headers["content-type"] == "image/webp"
        assert response.headers["content-disposition"] == 'inline; filename="image.webp"'
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cache-control"] == "no-store"

    def test_arbitrary_attachment_with_image_mime_is_still_forced_to_download(self) -> None:
        self.use_case.get_file_content.return_value = KnowledgeFileContent(
            file=self.file(
                kind=KnowledgeFileKind.ATTACHMENT,
                relative_path="attachments/unverified.webp",
                mime_type="image/webp",
                original_name="unverified.webp",
            ),
            content=content_chunks(),
        )

        response = self.api.client.get(
            "/api/knowledge/files/11111111111111111111111111111111/content",
        )

        self.asserts.status(response=response, expected_status=codes.OK)
        assert response.headers["content-type"] == "application/octet-stream"
        assert response.headers["content-disposition"].startswith("attachment;")

    def test_raw_attachment_cannot_spoof_editor_image_inline_delivery(self) -> None:
        self.use_case.get_file_content.return_value = KnowledgeFileContent(
            file=self.file(
                kind=KnowledgeFileKind.ATTACHMENT,
                processing=KnowledgeFileProcessing.RAW,
                relative_path="editor-images/spoofed.webp",
                mime_type="image/webp",
                original_name="spoofed.webp",
            ),
            content=content_chunks(),
        )

        response = self.api.client.get(
            "/api/knowledge/files/11111111111111111111111111111111/content",
        )

        self.asserts.status(response=response, expected_status=codes.OK)
        assert response.headers["content-type"] == "application/octet-stream"
        assert response.headers["content-disposition"].startswith("attachment;")

    def test_foreign_file_is_indistinguishable_from_missing_file(self) -> None:
        self.use_case.get_file_content.side_effect = KnowledgeFileNotFoundError

        response = self.api.client.get(
            "/api/knowledge/files/11111111111111111111111111111111/content",
        )

        self.asserts.error_message(
            response=response,
            expected_status=codes.NOT_FOUND,
            expected_message=KnowledgeFileNotFoundError.message,
        )

    def test_attachment_upload_returns_only_protected_content_path(self) -> None:
        file = self.file(kind=KnowledgeFileKind.ATTACHMENT)
        self.use_case.upload_attachment.return_value = file

        response = self.api.client.post(
            f"/api/knowledge/items/{file.item_id}/attachments",
            data={"name": "Résumé"},
            files={"file": ("private.html", b"<script>", "text/html")},
        )

        self.asserts.status(response=response, expected_status=codes.CREATED)
        body = response.json()
        assert body["contentPath"] == f"/api/knowledge/files/{file.id}/content"
        assert "relativePath" not in body
        assert "url" not in body

    def test_editor_image_upload_returns_attachment_metadata_and_protected_content_path(
        self,
    ) -> None:
        file = self.file(
            kind=KnowledgeFileKind.ATTACHMENT,
            processing=KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE,
            relative_path="editor-images/private.webp",
            mime_type="image/webp",
            original_name="private.png",
        )
        self.use_case.upload_attachment.return_value = file

        response = self.api.client.post(
            f"/api/knowledge/items/{file.item_id}/editor-images",
            files={"file": ("private.png", b"png-bytes", "image/png")},
        )

        self.asserts.status(response=response, expected_status=codes.CREATED)
        body = response.json()
        assert body["kind"] == KnowledgeFileKind.ATTACHMENT
        assert body["processing"] == KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE
        assert body["mimeType"] == "image/webp"
        assert body["contentPath"] == f"/api/knowledge/files/{file.id}/content"
        params = self.use_case.upload_attachment.await_args.kwargs["params"]
        assert params.item_id == file.item_id
        assert params.author_username == TEST_OWNER_USERNAME
        assert params.kind == KnowledgeFileKind.ATTACHMENT
        assert params.original_name == "private.png"
        assert params.mime_type == "image/png"
        assert params.content == b"png-bytes"
        assert (
            self.use_case.upload_attachment.await_args.kwargs["processing"]
            == KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE
        )
        assert (
            self.use_case.upload_attachment.await_args.kwargs["rollback_registrar"]
            is self.rollback_registrar
        )
        assert self.use_case.upload_attachment.await_args.kwargs["current_datetime"] == NOW

    def test_editor_image_upload_rejects_disallowed_declared_mime(self) -> None:
        response = self.api.client.post(
            f"/api/knowledge/items/{'2' * 32}/editor-images",
            files={"file": ("private.gif", b"gif-bytes", "image/gif")},
        )

        self.asserts.status(response=response, expected_status=codes.BAD_REQUEST)
        self.use_case.upload_attachment.assert_not_awaited()

    def test_editor_image_upload_hides_foreign_or_missing_item(self) -> None:
        self.use_case.upload_attachment.side_effect = KnowledgeItemNotFoundError

        response = self.api.client.post(
            f"/api/knowledge/items/{'2' * 32}/editor-images",
            files={"file": ("private.png", b"png-bytes", "image/png")},
        )

        self.asserts.error_message(
            response=response,
            expected_status=codes.NOT_FOUND,
            expected_message=KnowledgeItemNotFoundError.message,
        )
        assert (
            self.use_case.upload_attachment.await_args.kwargs["params"].author_username
            == TEST_OWNER_USERNAME
        )

    def test_attachment_upload_accepts_body_above_litestar_default_limit(self) -> None:
        file = self.file(kind=KnowledgeFileKind.ATTACHMENT)
        self.use_case.upload_attachment.return_value = file

        response = self.api.client.post(
            f"/api/knowledge/items/{file.item_id}/attachments",
            data={"name": "Large"},
            files={
                "file": (
                    "large.bin",
                    b"x" * 10_000_001,
                    "application/octet-stream",
                ),
            },
        )

        self.asserts.status(response=response, expected_status=codes.CREATED)

    @pytest.mark.parametrize(
        ("filename", "mime_type"),
        [
            ("x" * 256, "application/octet-stream"),
            ("file.bin", "x" * 256),
        ],
    )
    def test_attachment_upload_rejects_unpersistable_metadata(
        self,
        filename: str,
        mime_type: str,
    ) -> None:
        response = self.api.client.post(
            f"/api/knowledge/items/{'2' * 32}/attachments",
            data={"name": "File"},
            files={"file": (filename, b"x", mime_type)},
        )

        self.asserts.status(response=response, expected_status=codes.BAD_REQUEST)
        self.use_case.upload_attachment.assert_not_awaited()

    def test_attachment_upload_passes_request_rollback_registrar(self) -> None:
        file = self.file(kind=KnowledgeFileKind.ATTACHMENT)
        self.use_case.upload_attachment.return_value = file

        response = self.api.client.post(
            f"/api/knowledge/items/{file.item_id}/attachments",
            data={"name": "Private"},
            files={"file": ("private.bin", b"x", "application/octet-stream")},
        )

        self.asserts.status(response=response, expected_status=codes.CREATED)
        assert (
            self.use_case.upload_attachment.await_args.kwargs["rollback_registrar"]
            is self.rollback_registrar
        )
        current_datetime = self.use_case.upload_attachment.await_args.kwargs["current_datetime"]
        assert current_datetime == NOW

    def test_attachment_delete_schedules_cleanup_after_commit(self) -> None:
        file = self.file(kind=KnowledgeFileKind.ATTACHMENT)
        self.use_case.delete_attachment.return_value = KnowledgeFileMutationResult(
            file=None,
            object_names_to_delete=(file.relative_path,),
        )

        with patch.object(PostCommitActions, "add", autospec=True) as add_action:
            response = self.api.client.delete(
                f"/api/knowledge/items/{file.item_id}/attachments/{file.id}",
            )

        self.asserts.status(response=response, expected_status=codes.NO_CONTENT)
        current_datetime = self.use_case.delete_attachment.await_args.kwargs["current_datetime"]
        assert current_datetime == NOW
        action = add_action.call_args.kwargs["action"]
        assert isinstance(action, partial)
        assert action.keywords == {"object_names": (file.relative_path,)}
