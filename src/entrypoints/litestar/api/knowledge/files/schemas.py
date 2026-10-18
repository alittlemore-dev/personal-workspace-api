from typing import Annotated, Self, cast

from litestar.datastructures.upload_file import UploadFile
from pydantic import ConfigDict, Field, model_validator

from core.knowledge.files.enums import KnowledgeFileKind, KnowledgeFileProcessing
from core.knowledge.files.schemas import (
    KnowledgeFile,
    KnowledgeFileUpdateParams,
    KnowledgeFileUploadParams,
)
from entrypoints.litestar.api.schemas import CamelCaseSchema
from entrypoints.litestar.api.validation import RequiredShortText
from infra.config.constants import constants


class KnowledgeFileResponseSchema(CamelCaseSchema):
    id: Annotated[
        str,
        Field(
            title="Identifier",
            description="Opaque resource identifier; use the value returned by this API.",
            examples=["4e92d4de561f4bc7a3eed227868952db"],
        ),
    ]
    item_id: Annotated[
        str,
        Field(
            title="Knowledge item identifier",
            description="Item id; use the identifier returned by the corresponding API.",
            examples=["1bb209e394954b71bd78b52d572dd835"],
        ),
    ]
    kind: Annotated[
        KnowledgeFileKind,
        Field(
            title="File kind",
            description="Kind; allowed values are listed in the referenced enumeration.",
            examples=["attachment"],
        ),
    ]
    processing: Annotated[
        KnowledgeFileProcessing,
        Field(
            title="File processing provenance",
            description="Processing; allowed values are listed in the referenced enumeration.",
            examples=["raw"],
        ),
    ]
    mime_type: Annotated[
        str,
        Field(
            title="MIME type",
            description=(
                "Stored file MIME type. Content downloads may use "
                "application/octet-stream for safe attachment delivery."
            ),
            examples=["application/pdf"],
        ),
    ]
    size_bytes: Annotated[
        int,
        Field(title="Size in bytes", description="Stored file size in bytes.", examples=[184320]),
    ]
    name: Annotated[
        str,
        Field(title="Display name", description="Human-readable name.", examples=["Project notes"]),
    ]
    original_name: Annotated[
        str,
        Field(
            title="Original name",
            description="Original filename supplied by the uploader.",
            examples=["project-notes.pdf"],
        ),
    ]
    content_path: Annotated[
        str,
        Field(
            title="Protected content path",
            description=(
                "Protected content URL path; requires bearer authentication and "
                "access to this file."
            ),
            examples=["/api/knowledge/files/4e92d4de561f4bc7a3eed227868952db/content"],
        ),
    ]
    created_at: Annotated[
        str,
        Field(
            title="Created at",
            description="Creation timestamp in ISO 8601 format.",
            examples=["2026-10-18T09:00:00Z"],
        ),
    ]
    updated_at: Annotated[
        str,
        Field(
            title="Updated at",
            description="Last modification timestamp in ISO 8601 format.",
            examples=["2026-10-18T10:30:00Z"],
        ),
    ]

    @classmethod
    def from_domain_schema(cls, *, schema: KnowledgeFile) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                id=schema.id,
                item_id=schema.item_id,
                kind=schema.kind,
                processing=schema.processing,
                mime_type=schema.mime_type,
                size_bytes=schema.size_bytes,
                name=schema.name,
                original_name=schema.original_name,
                content_path=f"/api/knowledge/files/{schema.id}/content",
                created_at=schema.created_at.isoformat(),
                updated_at=schema.updated_at.isoformat(),
            ),
        )


class KnowledgeUploadRequestSchema(CamelCaseSchema):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    file: Annotated[
        UploadFile,
        Field(
            title="Uploaded file",
            description=(
                "Binary file part in multipart/form-data; select a local file, not a JSON filename."
            ),
        ),
    ]

    @model_validator(mode="after")
    def validate_file_metadata(self) -> Self:  # noqa: N804
        original_name = self.file.filename
        mime_type = self.file.content_type or "application/octet-stream"
        if not original_name or (
            len(original_name) > constants.knowledge_files.original_name_max_length
        ):
            message = "Uploaded file name is invalid"
            raise ValueError(message)
        if len(mime_type) > constants.knowledge_files.mime_type_max_length:
            message = "Uploaded file MIME type is invalid"
            raise ValueError(message)
        return self

    async def build_upload_params(  # noqa: PLR0913
        self,
        *,
        file_id: str,
        item_id: str,
        author_username: str,
        kind: KnowledgeFileKind,
        name: str,
        max_size_bytes: int,
    ) -> KnowledgeFileUploadParams:
        original_name = self.file.filename
        return KnowledgeFileUploadParams(
            id=file_id,
            item_id=item_id,
            author_username=author_username,
            kind=kind,
            name=name,
            original_name=original_name,
            mime_type=self.file.content_type or "application/octet-stream",
            content=await self.file.read(max_size_bytes + 1),
        )


class KnowledgeAttachmentUploadRequestSchema(KnowledgeUploadRequestSchema):
    name: Annotated[
        RequiredShortText,
        Field(title="Display name", description="Human-readable name.", examples=["Project notes"]),
    ]

    async def to_domain_schema(
        self,
        *,
        file_id: str,
        item_id: str,
        author_username: str,
    ) -> KnowledgeFileUploadParams:
        return await self.build_upload_params(
            file_id=file_id,
            item_id=item_id,
            author_username=author_username,
            kind=KnowledgeFileKind.ATTACHMENT,
            name=self.name,
            max_size_bytes=constants.knowledge_files.attachment_max_size_bytes,
        )


class KnowledgePhotoUploadRequestSchema(KnowledgeUploadRequestSchema):
    async def to_domain_schema(
        self,
        *,
        file_id: str,
        person_id: str,
        author_username: str,
    ) -> KnowledgeFileUploadParams:
        original_name = self.file.filename
        return await self.build_upload_params(
            file_id=file_id,
            item_id=person_id,
            author_username=author_username,
            kind=KnowledgeFileKind.PERSON_PHOTO,
            name=original_name,
            max_size_bytes=constants.knowledge_files.photo_max_size_bytes,
        )


class KnowledgeEditorImageUploadRequestSchema(KnowledgeUploadRequestSchema):
    @model_validator(mode="after")
    def validate_allowed_mime_type(self) -> Self:  # noqa: N804
        mime_type = self.file.content_type or "application/octet-stream"
        if mime_type not in constants.knowledge_files.photo_mime_types:
            message = "Uploaded editor image MIME type is not allowed"
            raise ValueError(message)
        return self

    async def to_domain_schema(
        self,
        *,
        file_id: str,
        item_id: str,
        author_username: str,
    ) -> KnowledgeFileUploadParams:
        original_name = self.file.filename
        return await self.build_upload_params(
            file_id=file_id,
            item_id=item_id,
            author_username=author_username,
            kind=KnowledgeFileKind.ATTACHMENT,
            name=original_name,
            max_size_bytes=constants.knowledge_files.photo_max_size_bytes,
        )


class KnowledgeFileUpdateRequestSchema(CamelCaseSchema):
    name: Annotated[
        RequiredShortText,
        Field(title="Display name", description="Human-readable name.", examples=["Project notes"]),
    ]

    def to_domain_schema(self) -> KnowledgeFileUpdateParams:
        return KnowledgeFileUpdateParams(name=self.name)
