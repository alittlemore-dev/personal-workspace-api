from datetime import datetime
from typing import Annotated, Self

from litestar.datastructures.upload_file import UploadFile
from pydantic import ConfigDict, Field, HttpUrl

from core.files.enums import FilePurpose
from core.files.schemas import FileRead
from entrypoints.litestar.api.schemas import CamelCaseSchema


class FileUploadRequestSchema(CamelCaseSchema):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    purpose: Annotated[
        FilePurpose,
        Field(
            title="File purpose",
            description="Purpose; allowed values are listed in the referenced enumeration.",
            examples=["attachment"],
        ),
    ]
    name: Annotated[
        str,
        Field(title="Display name", description="Human-readable name.", examples=["Project notes"]),
    ]
    file: Annotated[
        UploadFile,
        Field(
            title="Uploaded file",
            description=(
                "Binary file part in multipart/form-data; select a local file, not a JSON filename."
            ),
        ),
    ]


class FileResponseSchema(CamelCaseSchema):
    id: Annotated[
        str,
        Field(
            title="File ID",
            description="Opaque resource identifier; use the value returned by this API.",
            examples=["4e92d4de561f4bc7a3eed227868952db"],
        ),
    ]
    purpose: Annotated[
        FilePurpose,
        Field(
            title="File purpose",
            description="Purpose; allowed values are listed in the referenced enumeration.",
            examples=["attachment"],
        ),
    ]
    namespace: Annotated[
        str,
        Field(
            title="Storage namespace",
            description="Storage namespace for the managed file.",
            examples=["media"],
        ),
    ]
    relative_path: Annotated[
        str,
        Field(
            title="Storage-relative object path",
            description="Object path relative to the storage namespace.",
            examples=["attachments/4e92d4de561f4bc7a3eed227868952db.pdf"],
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
        Field(
            title="File size in bytes",
            description="Stored file size in bytes.",
            examples=[184320],
        ),
    ]
    name: Annotated[
        str,
        Field(title="Display name", description="Human-readable name.", examples=["Project notes"]),
    ]
    original_name: Annotated[
        str,
        Field(
            title="Original upload name",
            description="Original filename supplied by the uploader.",
            examples=["project-notes.pdf"],
        ),
    ]
    access_url: Annotated[
        HttpUrl,
        Field(
            title="Access URL",
            description="Uploaded file access URL",
            examples=["https://example.com/path/to/file"],
        ),
    ]
    markdown_url: Annotated[
        HttpUrl,
        Field(
            title="Markdown URL",
            description="File URL with the file ID marker for markdown content.",
            examples=["https://example.com/path/to/file#fileId=00000000000000000000000000000001"],
        ),
    ]
    created_at: Annotated[
        datetime,
        Field(
            title="Created at",
            description="Creation timestamp in ISO 8601 format.",
            examples=["2026-10-18T09:00:00Z"],
        ),
    ]
    updated_at: Annotated[
        datetime,
        Field(
            title="Updated at",
            description="Last modification timestamp in ISO 8601 format.",
            examples=["2026-10-18T10:30:00Z"],
        ),
    ]

    @classmethod
    def from_domain_schema(cls, *, schema: FileRead) -> Self:
        return cls(
            id=schema.file.id,
            purpose=schema.file.purpose,
            namespace=schema.file.namespace,
            relative_path=schema.file.relative_path,
            mime_type=schema.file.mime_type,
            size_bytes=schema.file.size_bytes,
            name=schema.file.name,
            original_name=schema.file.original_name,
            access_url=HttpUrl(schema.access_url),
            markdown_url=HttpUrl(schema.markdown_url),
            created_at=schema.file.created_at,
            updated_at=schema.file.updated_at,
        )


class FilesResponseSchema(CamelCaseSchema):
    files: Annotated[
        list[FileResponseSchema],
        Field(title="Files", description="Files returned by this operation."),
    ]

    @classmethod
    def from_domain_schema(cls, *, schema: list[FileRead]) -> Self:
        return cls(
            files=[FileResponseSchema.from_domain_schema(schema=file) for file in schema],
        )


class FileUpdateRequestSchema(CamelCaseSchema):
    name: Annotated[
        str,
        Field(title="Display name", description="Human-readable name.", examples=["Project notes"]),
    ]
