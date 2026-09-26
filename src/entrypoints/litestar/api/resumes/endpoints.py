from datetime import datetime
from typing import Annotated

from dishka import FromDishka
from dishka.integrations.litestar import DishkaRouter
from litestar import Controller, Request, Response, delete, get, post, put, status_codes
from litestar.di import NamedDependency, Provide

from core.files.enums import FilePurpose
from core.files.exceptions import InvalidFileDataError
from core.files.schemas import FileUploadParams
from core.generators import HexUuidIdGenerator
from core.resumes.schemas import ResumeFilters
from core.resumes.use_cases import ResumesUseCase
from entrypoints.litestar.api.parameters import ResumeIdPath, api_json_body, api_multipart_body
from entrypoints.litestar.api.resumes.dependencies import provide_resume_filters
from entrypoints.litestar.api.resumes.responses import ResumeExportResponse
from entrypoints.litestar.api.resumes.schemas import (
    ResumeExportRequestSchema,
    ResumePhotoUploadRequestSchema,
    ResumeRequestSchema,
    ResumeResponseSchema,
    ResumesResponseSchema,
)


class ResumesApiController(Controller):
    path = "/resumes"
    tags = ["resumes"]

    @get(
        "",
        description="Get the resume list.",
        name="resumes-list-api-handler",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"filters": Provide(provide_resume_filters, sync_to_thread=False)},
    )
    async def list_resumes(
        self,
        use_case: FromDishka[ResumesUseCase],
        filters: NamedDependency[ResumeFilters],
    ) -> ResumesResponseSchema:
        resumes = await use_case.list_resumes(filters=filters)
        return ResumesResponseSchema.from_domain_schema(schema=resumes)

    @post(
        "",
        description="Create a resume.",
        name="resumes-create-api-handler",
        status_code=status_codes.HTTP_201_CREATED,
    )
    async def create_resume(
        self,
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
        request: Request,
        use_case: FromDishka[ResumesUseCase],
    ) -> ResumeResponseSchema:
        resume = await use_case.create_resume(
            params=data.to_create_schema(author_username=request.user.username),
        )
        return ResumeResponseSchema.from_domain_schema(schema=resume)

    @get(
        "/{resume_id:str}",
        description="Get resume details.",
        name="resumes-detail-api-handler",
        status_code=status_codes.HTTP_200_OK,
    )
    async def get_resume(
        self,
        resume_id: ResumeIdPath,
        request: Request,
        use_case: FromDishka[ResumesUseCase],
    ) -> ResumeResponseSchema:
        resume = await use_case.get_resume(
            resume_id=resume_id,
            author_username=request.user.username,
        )
        return ResumeResponseSchema.from_domain_schema(schema=resume)

    @post(
        "/{resume_id:str}/photo",
        description="Upload a private resume photo.",
        name="resumes-photo-upload-api-handler",
        status_code=status_codes.HTTP_200_OK,
        request_max_body_size=1_048_576,
    )
    async def upload_photo(  # noqa: PLR0913
        self,
        resume_id: ResumeIdPath,
        data: Annotated[
            ResumePhotoUploadRequestSchema,
            api_multipart_body(
                title="Resume photo upload",
                description="JPEG resume photo.",
                examples=({"file": "photo.jpg"},),
            ),
        ],
        request: Request,
        use_case: FromDishka[ResumesUseCase],
        id_generator: FromDishka[HexUuidIdGenerator],
        current_datetime: FromDishka[datetime],
    ) -> ResumeResponseSchema:
        if not data.file.filename:
            raise InvalidFileDataError
        resume = await use_case.upload_photo(
            resume_id=resume_id,
            author_username=request.user.username,
            params=FileUploadParams(
                id=id_generator.get_next(),
                purpose=FilePurpose.ATTACHMENT,
                name="Resume photo",
                original_name=data.file.filename,
                mime_type=data.file.content_type or "application/octet-stream",
                content=await data.file.read(),
            ),
            current_datetime=current_datetime,
        )
        return ResumeResponseSchema.from_domain_schema(schema=resume)

    @get(
        "/{resume_id:str}/photo",
        description="Read a private resume photo.",
        name="resumes-photo-read-api-handler",
    )
    async def get_photo(
        self,
        resume_id: ResumeIdPath,
        request: Request,
        use_case: FromDishka[ResumesUseCase],
    ) -> Response[bytes]:
        content = await use_case.read_photo(
            resume_id=resume_id, author_username=request.user.username
        )
        return Response(
            content=content,
            media_type="image/jpeg",
            headers={"Cache-Control": "private, no-store"},
        )

    @put(
        "/{resume_id:str}",
        description="Update a resume.",
        name="resumes-update-api-handler",
        status_code=status_codes.HTTP_200_OK,
    )
    async def update_resume(
        self,
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
        request: Request,
        use_case: FromDishka[ResumesUseCase],
        current_datetime: FromDishka[datetime],
    ) -> ResumeResponseSchema:
        resume = await use_case.update_resume(
            resume_id=resume_id,
            params=data.to_update_schema(),
            author_username=request.user.username,
            current_datetime=current_datetime,
        )
        return ResumeResponseSchema.from_domain_schema(schema=resume)

    @post(
        "/{resume_id:str}/export",
        description="Export a resume.",
        name="resumes-export-api-handler",
        status_code=status_codes.HTTP_200_OK,
    )
    async def export_resume(
        self,
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
        request: Request,
        use_case: FromDishka[ResumesUseCase],
    ) -> ResumeExportResponse:
        document = await use_case.export_resume(
            resume_id=resume_id,
            params=data.to_export_schema(),
            author_username=request.user.username,
        )
        return ResumeExportResponse.from_resume_export(
            resume_id=resume_id,
            document=document,
        )

    @delete(
        "/{resume_id:str}",
        description="Delete a resume.",
        name="resumes-delete-api-handler",
        status_code=status_codes.HTTP_204_NO_CONTENT,
    )
    async def delete_resume(
        self,
        resume_id: ResumeIdPath,
        request: Request,
        use_case: FromDishka[ResumesUseCase],
        current_datetime: FromDishka[datetime],
    ) -> None:
        await use_case.delete_resume(
            resume_id=resume_id,
            author_username=request.user.username,
            current_datetime=current_datetime,
        )


api_router = DishkaRouter("", route_handlers=[ResumesApiController])
