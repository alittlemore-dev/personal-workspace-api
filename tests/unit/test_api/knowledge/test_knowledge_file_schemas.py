import pytest
from litestar.datastructures import UploadFile
from pydantic import ValidationError

from core.knowledge.files.enums import KnowledgeFileKind
from core.knowledge.files.schemas import KnowledgeFileUploadParams
from entrypoints.litestar.api.knowledge.files.schemas import (
    KnowledgeAttachmentUploadRequestSchema,
    KnowledgeEditorImageUploadRequestSchema,
    KnowledgePhotoUploadRequestSchema,
)
from infra.config.constants import constants


class RecordingUploadFile(UploadFile):
    read_size: int | None = None

    async def read(self, size: int = -1) -> bytes:
        self.read_size = size
        return await super().read(size)


@pytest.mark.parametrize(
    ("filename", "mime_type"),
    [
        ("x" * 256, "application/octet-stream"),
        ("file.bin", "x" * 256),
    ],
)
def test_attachment_schema_rejects_unpersistable_file_metadata(
    filename: str,
    mime_type: str,
) -> None:
    upload_file = UploadFile(
        filename=filename,
        content_type=mime_type,
        file_data=b"x",
    )
    try:
        with pytest.raises(ValidationError):
            KnowledgeAttachmentUploadRequestSchema(
                name="Private",
                file=upload_file,
            )
    finally:
        upload_file.file.close()


async def test_attachment_schema_builds_bounded_domain_upload_params() -> None:
    upload_file = RecordingUploadFile(
        filename="private.txt",
        content_type="text/plain",
        file_data=b"private",
    )
    try:
        schema = KnowledgeAttachmentUploadRequestSchema(name="Notes", file=upload_file)

        result = await schema.to_domain_schema(
            file_id="1" * 32,
            item_id="2" * 32,
            author_username="owner",
        )

        assert result == KnowledgeFileUploadParams(
            id="1" * 32,
            item_id="2" * 32,
            author_username="owner",
            kind=KnowledgeFileKind.ATTACHMENT,
            name="Notes",
            original_name="private.txt",
            mime_type="text/plain",
            content=b"private",
        )
        assert upload_file.read_size == constants.knowledge_files.attachment_max_size_bytes + 1
    finally:
        upload_file.file.close()


async def test_photo_schema_builds_domain_upload_params_with_filename_as_name() -> None:
    upload_file = UploadFile(
        filename="portrait.png",
        content_type="image/png",
        file_data=b"png",
    )
    try:
        schema = KnowledgePhotoUploadRequestSchema(file=upload_file)

        result = await schema.to_domain_schema(
            file_id="1" * 32,
            person_id="2" * 32,
            author_username="owner",
        )

        assert result.kind == KnowledgeFileKind.PERSON_PHOTO
        assert result.name == "portrait.png"
        assert result.original_name == "portrait.png"
        assert result.mime_type == "image/png"
        assert result.content == b"png"
    finally:
        upload_file.file.close()


async def test_editor_image_schema_builds_bounded_attachment_upload_params() -> None:
    upload_file = RecordingUploadFile(
        filename="diagram.png",
        content_type="image/png",
        file_data=b"png",
    )
    try:
        schema = KnowledgeEditorImageUploadRequestSchema(file=upload_file)

        result = await schema.to_domain_schema(
            file_id="1" * 32,
            item_id="2" * 32,
            author_username="owner",
        )

        assert result == KnowledgeFileUploadParams(
            id="1" * 32,
            item_id="2" * 32,
            author_username="owner",
            kind=KnowledgeFileKind.ATTACHMENT,
            name="diagram.png",
            original_name="diagram.png",
            mime_type="image/png",
            content=b"png",
        )
        assert upload_file.read_size == constants.knowledge_files.photo_max_size_bytes + 1
    finally:
        upload_file.file.close()


def test_editor_image_schema_rejects_non_raster_mime() -> None:
    upload_file = UploadFile(
        filename="diagram.gif",
        content_type="image/gif",
        file_data=b"gif",
    )
    try:
        with pytest.raises(ValidationError):
            KnowledgeEditorImageUploadRequestSchema(file=upload_file)
    finally:
        upload_file.file.close()
