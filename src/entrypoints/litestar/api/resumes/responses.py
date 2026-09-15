from typing import Self

from litestar import Response

from core.resumes.enums import ResumeExportFormatEnum
from core.resumes.schemas import ResumeExport
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

        return cls(
            content=document.content,
            media_type=media_type,
            headers={
                constants.resume_export.content_disposition_header_name: (
                    f'attachment; filename="resume-{resume_id}.{extension}"'
                ),
            },
        )
