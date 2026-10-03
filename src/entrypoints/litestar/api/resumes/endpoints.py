from typing import Annotated

from backend_sdk import Principal
from backend_sdk.integrations.litestar import AuthContext
from dishka import FromDishka
from dishka.integrations.litestar import DishkaRouter
from litestar import Controller, Request, Response, delete, get, post, put, status_codes
from litestar.datastructures import State
from litestar.di import NamedDependency, Provide

from core.resumes.schemas import (
    DeleteResumeParams,
    ExportResumeParams,
    ResumeFilters,
    ResumeTargetParams,
    UpdateResumeParams,
    UploadResumePhotoParams,
)
from core.resumes.use_cases import ResumesUseCase
from entrypoints.litestar.api.parameters import ResumeIdPath, api_json_body, api_multipart_body
from entrypoints.litestar.api.resumes.dependencies import (
    provide_delete_resume_params,
    provide_export_resume_params,
    provide_get_photo_params,
    provide_get_resume_params,
    provide_resume_filters,
    provide_update_resume_params,
    provide_upload_photo_params,
)
from entrypoints.litestar.api.resumes.responses import ResumeExportResponse
from entrypoints.litestar.api.resumes.schemas import (
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
                            "settings": {"dateFormat": "monthYear"},
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
        dependencies={"params": Provide(provide_get_resume_params, sync_to_thread=False)},
    )
    async def get_resume(
        self,
        use_case: FromDishka[ResumesUseCase],
        params: NamedDependency[ResumeTargetParams],
    ) -> ResumeResponseSchema:
        resume = await use_case.get_resume(
            params=params,
        )
        return ResumeResponseSchema.from_domain_schema(schema=resume)

    @post(
        "/{resume_id:str}/photo",
        description="Upload a private resume photo.",
        name="resumes-photo-upload-api-handler",
        status_code=status_codes.HTTP_200_OK,
        request_max_body_size=1_048_576,
        dependencies={"params": Provide(provide_upload_photo_params)},
    )
    async def upload_photo(
        self,
        # Litestar requires this handler metadata to decode the dependency's multipart body.
        data: Annotated[  # noqa: ARG002
            ResumePhotoUploadRequestSchema,
            api_multipart_body(
                title="Resume photo upload",
                description="JPEG resume photo.",
                examples=({"file": "photo.jpg"},),
            ),
        ],
        use_case: FromDishka[ResumesUseCase],
        params: NamedDependency[UploadResumePhotoParams],
    ) -> ResumeResponseSchema:
        resume = await use_case.upload_photo(
            params=params,
        )
        return ResumeResponseSchema.from_domain_schema(schema=resume)

    @get(
        "/{resume_id:str}/photo",
        description="Read a private resume photo.",
        name="resumes-photo-read-api-handler",
        dependencies={"params": Provide(provide_get_photo_params, sync_to_thread=False)},
    )
    async def get_photo(
        self,
        use_case: FromDishka[ResumesUseCase],
        params: NamedDependency[ResumeTargetParams],
    ) -> Response[bytes]:
        content = await use_case.read_photo(
            params=params,
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
        dependencies={"params": Provide(provide_update_resume_params)},
    )
    async def update_resume(
        self,
        use_case: FromDishka[ResumesUseCase],
        params: NamedDependency[UpdateResumeParams],
    ) -> ResumeResponseSchema:
        resume = await use_case.update_resume(
            params=params,
        )
        return ResumeResponseSchema.from_domain_schema(schema=resume)

    @post(
        "/{resume_id:str}/export",
        description="Export a resume.",
        name="resumes-export-api-handler",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_export_resume_params, sync_to_thread=False)},
    )
    async def export_resume(
        self,
        resume_id: ResumeIdPath,
        use_case: FromDishka[ResumesUseCase],
        params: NamedDependency[ExportResumeParams],
    ) -> ResumeExportResponse:
        document = await use_case.export_resume(
            params=params,
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
        dependencies={"params": Provide(provide_delete_resume_params)},
    )
    async def delete_resume(
        self,
        use_case: FromDishka[ResumesUseCase],
        params: NamedDependency[DeleteResumeParams],
    ) -> None:
        await use_case.delete_resume(
            params=params,
        )


api_router = DishkaRouter("", route_handlers=[ResumesApiController])
