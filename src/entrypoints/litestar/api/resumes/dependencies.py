from datetime import datetime
from typing import Annotated

from backend_sdk import Principal
from backend_sdk.integrations.litestar import AuthContext
from dishka import FromDishka
from dishka.integrations.litestar import inject
from litestar import Request
from litestar.datastructures import State

from core.files.enums import FilePurpose
from core.files.exceptions import InvalidFileDataError
from core.files.schemas import FileUploadParams
from core.generators import HexUuidIdGenerator
from core.resumes.schemas import (
    DeleteResumeParams,
    ExportResumeParams,
    ResumeFilters,
    ResumeTargetParams,
    UpdateResumeParams,
    UploadResumePhotoParams,
)
from entrypoints.litestar.api.parameters import (
    PageQuery,
    PageSizeQuery,
    ResumeIdPath,
    api_json_body,
    api_multipart_body,
)
from entrypoints.litestar.api.resumes.schemas import (
    ResumeExportRequestSchema,
    ResumePhotoUploadRequestSchema,
    ResumeRequestSchema,
)


def provide_resume_filters(
    request: Request[Principal, AuthContext, State],
    page: PageQuery,
    page_size: PageSizeQuery,
) -> ResumeFilters:
    return ResumeFilters(
        page=page,
        page_size=page_size,
        search_query=None,
        author_username=request.user.username,
    )


def provide_get_resume_params(
    resume_id: ResumeIdPath,
    request: Request[Principal, AuthContext, State],
) -> ResumeTargetParams:
    return ResumeTargetParams(
        resume_id=resume_id,
        author_username=request.user.username,
    )


@inject
async def provide_upload_photo_params(
    resume_id: ResumeIdPath,
    data: Annotated[
        ResumePhotoUploadRequestSchema,
        api_multipart_body(
            title="Resume photo upload",
            description="JPEG resume photo.",
            examples=({"file": "photo.jpg"},),
        ),
    ],
    request: Request[Principal, AuthContext, State],
    id_generator: FromDishka[HexUuidIdGenerator],
    current_datetime: FromDishka[datetime],
) -> UploadResumePhotoParams:
    if not data.file.filename:
        raise InvalidFileDataError
    return UploadResumePhotoParams(
        resume_id=resume_id,
        author_username=request.user.username,
        data=FileUploadParams(
            id=id_generator.get_next(),
            purpose=FilePurpose.ATTACHMENT,
            name="Resume photo",
            original_name=data.file.filename,
            mime_type=data.file.content_type or "application/octet-stream",
            content=await data.file.read(),
        ),
        current_datetime=current_datetime,
    )


def provide_get_photo_params(
    resume_id: ResumeIdPath,
    request: Request[Principal, AuthContext, State],
) -> ResumeTargetParams:
    return ResumeTargetParams(
        resume_id=resume_id,
        author_username=request.user.username,
    )


@inject
async def provide_update_resume_params(
    resume_id: ResumeIdPath,
    data: Annotated[
        ResumeRequestSchema,
        api_json_body(
            title="Resume request",
            description="Structured resume workspace payload.",
            examples=(
                {
                    "title": "Backend Engineer",
                    "language": "en",
                    "content": {
                        "settings": {
                            "dateFormat": "monthYear",
                            "sectionOrder": [],
                            "hiddenSections": [],
                        },
                        "profile": {
                            "fullName": "Dmitriy Lunev",
                            "headline": "Backend Engineer",
                            "location": "Moscow",
                            "email": "example@mail.ru",
                            "phone": "",
                            "telegram": "@alm_dmitriy_dev",
                            "website": "https://example.com",
                        },
                        "summary": {"text": "Builds reliable backend systems."},
                        "skills": [],
                        "experience": [],
                        "education": [],
                        "languages": [],
                        "certifications": [],
                        "additionalSections": [],
                    },
                },
            ),
        ),
    ],
    request: Request[Principal, AuthContext, State],
    current_datetime: FromDishka[datetime],
) -> UpdateResumeParams:
    return UpdateResumeParams(
        resume_id=resume_id,
        data=data.to_update_schema(),
        author_username=request.user.username,
        current_datetime=current_datetime,
    )


def provide_export_resume_params(
    resume_id: ResumeIdPath,
    data: Annotated[
        ResumeExportRequestSchema,
        api_json_body(
            title="Resume export request",
            description="Structured resume payload plus requested export format.",
            examples=(
                {
                    "title": "Backend Engineer",
                    "language": "en",
                    "format": "docx",
                    "theme": "simple",
                    "content": {
                        "settings": {
                            "dateFormat": "monthYear",
                            "sectionOrder": [],
                            "hiddenSections": [],
                        },
                        "profile": {
                            "fullName": "Dmitriy Lunev",
                            "headline": "Backend Engineer",
                            "location": "Moscow",
                            "email": "example@mail.ru",
                            "phone": "",
                            "telegram": "@alm_dmitriy_dev",
                            "website": "https://example.com",
                        },
                        "summary": {"text": "Builds reliable backend systems."},
                        "skills": [],
                        "experience": [],
                        "education": [],
                        "languages": [],
                        "certifications": [],
                        "additionalSections": [],
                    },
                },
            ),
        ),
    ],
    request: Request[Principal, AuthContext, State],
) -> ExportResumeParams:
    return ExportResumeParams(
        resume_id=resume_id,
        data=data.to_export_schema(),
        author_username=request.user.username,
    )


@inject
async def provide_delete_resume_params(
    resume_id: ResumeIdPath,
    request: Request[Principal, AuthContext, State],
    current_datetime: FromDishka[datetime],
) -> DeleteResumeParams:
    return DeleteResumeParams(
        resume_id=resume_id,
        author_username=request.user.username,
        current_datetime=current_datetime,
    )
