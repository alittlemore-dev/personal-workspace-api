from contextlib import suppress
from io import BytesIO
from typing import Self

from litestar import Response
from litestar.openapi.spec import OpenAPIHeader, Schema
from litestar.openapi.spec.enums import OpenAPIType
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from core.resumes.enums import ResumeExportFormatEnum
from core.resumes.schemas import ResumeExport
from entrypoints.litestar.openapi_responses import BinaryResponseMetadata
from infra.config.constants import constants


class ResumeExportResponse(Response[bytes]):
    @classmethod
    def from_resume_export(
        cls,
        *,
        resume_id: str,
        document: ResumeExport,
    ) -> Self:
        media_type: str = constants.resume_export.pdf_media_type
        extension: str = constants.resume_export.pdf_extension
        if document.format == ResumeExportFormatEnum.DOCX:
            media_type = constants.resume_export.docx_media_type
            extension = constants.resume_export.docx_extension

        headers: dict[str, str] = {
            constants.resume_export.content_disposition_header_name: (
                f'attachment; filename="resume-{resume_id}.{extension}"'
            ),
        }
        if document.format == ResumeExportFormatEnum.PDF:
            with suppress(PdfReadError):
                headers["X-Resume-Page-Count"] = str(
                    len(PdfReader(BytesIO(document.content)).pages),
                )

        return cls(
            content=document.content,
            media_type=media_type,
            headers=headers,
        )


RESUME_EXPORT_OPENAPI_RESPONSE = BinaryResponseMetadata(
    media_types=(constants.resume_export.pdf_media_type, constants.resume_export.docx_media_type),
    description=(
        "Rendered resume file. The request format selects application/pdf (pdf) or "
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document (docx). "
        "Content-Disposition contains the download filename. Export renders the supplied "
        "content without saving it to the stored resume."
    ),
    headers={
        "Content-Disposition": OpenAPIHeader(
            description="Attachment filename matching the requested export format.",
            schema=Schema(
                type=OpenAPIType.STRING,
                examples=['attachment; filename="resume-4e92d4de561f4bc7a3eed227868952db.pdf"'],
            ),
        ),
        "X-Resume-Page-Count": OpenAPIHeader(
            description=(
                "Number of PDF pages, when the generated PDF can be parsed. Omitted for DOCX."
            ),
            schema=Schema(type=OpenAPIType.INTEGER, examples=[2]),
        ),
    },
)

RESUME_PHOTO_OPENAPI_RESPONSE = BinaryResponseMetadata(
    media_types=("image/jpeg",),
    description="Private resume photograph as raw JPEG bytes.",
    headers={
        "Cache-Control": OpenAPIHeader(
            description="Private image must not be stored in caches.",
            schema=Schema(type=OpenAPIType.STRING, examples=["private, no-store"]),
        ),
    },
)
