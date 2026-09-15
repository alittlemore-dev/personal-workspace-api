from datetime import datetime
from typing import Annotated

from dishka import FromDishka
from litestar import Controller, Request, delete, get, post, put, status_codes
from litestar.di import NamedDependency, Provide

from core.knowledge.dates.schemas import KnowledgeDateFilters
from core.knowledge.dates.use_cases import KnowledgeDatesUseCase
from core.knowledge.files.clients import KnowledgeFileObjectCleaner
from entrypoints.litestar.api.knowledge.dates.dependencies import (
    provide_knowledge_date_filters,
)
from entrypoints.litestar.api.knowledge.dates.schemas import (
    KnowledgeDateCreateRequestSchema,
    KnowledgeDateResponseSchema,
    KnowledgeDatesResponseSchema,
    KnowledgeDateUpdateRequestSchema,
)
from entrypoints.litestar.api.knowledge.files.post_commit import (
    register_knowledge_object_cleanup,
)
from entrypoints.litestar.api.parameters import KnowledgeDateIdPath, api_json_body
from infra.config.constants import constants
from infra.post_commit_actions import PostCommitActions


class KnowledgeDatesApiController(Controller):
    path = "/knowledge/dates"
    tags = ["knowledge dates"]
    include_in_schema = False
    response_headers = {
        constants.knowledge_files.cache_control_header_name: (
            constants.knowledge_files.no_store_header_value
        ),
    }

    @get(
        "",
        description="List private memorable dates owned by the current author.",
        name="knowledge-dates-list-api-handler",
        status_code=status_codes.HTTP_200_OK,
        dependencies={
            "filters": Provide(provide_knowledge_date_filters, sync_to_thread=False),
        },
    )
    async def list_dates(
        self,
        use_case: FromDishka[KnowledgeDatesUseCase],
        filters: NamedDependency[KnowledgeDateFilters],
    ) -> KnowledgeDatesResponseSchema:
        return KnowledgeDatesResponseSchema.from_domain_schema(
            schema=await use_case.list_dates(filters=filters),
        )

    @post(
        "",
        description="Quick-create a private memorable date.",
        name="knowledge-dates-create-api-handler",
        status_code=status_codes.HTTP_201_CREATED,
    )
    async def create_date(
        self,
        data: Annotated[
            KnowledgeDateCreateRequestSchema,
            api_json_body(
                title="Knowledge date create request",
                description="Required title and annual date.",
                examples=(
                    {
                        "displayName": "Годовщина",
                        "date": {"day": 29, "month": 2, "year": None},
                    },
                ),
            ),
        ],
        request: Request,
        use_case: FromDishka[KnowledgeDatesUseCase],
        current_datetime: FromDishka[datetime],
    ) -> KnowledgeDateResponseSchema:
        return KnowledgeDateResponseSchema.from_domain_schema(
            schema=await use_case.create_date(
                params=data.to_domain_schema(author_username=request.user.username),
                today=current_datetime.date(),
            ),
        )

    @get(
        "/{date_id:str}",
        description="Get one private memorable date owned by the current author.",
        name="knowledge-dates-detail-api-handler",
        status_code=status_codes.HTTP_200_OK,
    )
    async def get_date(
        self,
        date_id: KnowledgeDateIdPath,
        request: Request,
        use_case: FromDishka[KnowledgeDatesUseCase],
    ) -> KnowledgeDateResponseSchema:
        return KnowledgeDateResponseSchema.from_domain_schema(
            schema=await use_case.get_date(
                date_id=date_id,
                author_username=request.user.username,
            ),
        )

    @put(
        "/{date_id:str}",
        description="Replace editable private memorable date data.",
        name="knowledge-dates-update-api-handler",
        status_code=status_codes.HTTP_200_OK,
    )
    async def update_date(
        self,
        date_id: KnowledgeDateIdPath,
        data: Annotated[
            KnowledgeDateUpdateRequestSchema,
            api_json_body(
                title="Knowledge date update request",
                description="Complete editable memorable date payload.",
                examples=(
                    {
                        "displayName": "Годовщина",
                        "date": {"day": 29, "month": 2, "year": None},
                        "description": "",
                        "tagIds": [],
                        "personIds": [],
                    },
                ),
            ),
        ],
        request: Request,
        use_case: FromDishka[KnowledgeDatesUseCase],
        current_datetime: FromDishka[datetime],
    ) -> KnowledgeDateResponseSchema:
        return KnowledgeDateResponseSchema.from_domain_schema(
            schema=await use_case.update_date(
                date_id=date_id,
                params=data.to_domain_schema(),
                author_username=request.user.username,
                current_datetime=current_datetime,
            ),
        )

    @delete(
        "/{date_id:str}",
        description="Permanently delete a private memorable date.",
        name="knowledge-dates-delete-api-handler",
        status_code=status_codes.HTTP_204_NO_CONTENT,
    )
    async def delete_date(  # noqa: PLR0913
        self,
        date_id: KnowledgeDateIdPath,
        request: Request,
        use_case: FromDishka[KnowledgeDatesUseCase],
        current_datetime: FromDishka[datetime],
        object_cleaner: FromDishka[KnowledgeFileObjectCleaner],
        post_commit_actions: FromDishka[PostCommitActions],
    ) -> None:
        object_names = await use_case.delete_date(
            date_id=date_id,
            author_username=request.user.username,
            current_datetime=current_datetime,
        )
        register_knowledge_object_cleanup(
            object_names=object_names,
            object_cleaner=object_cleaner,
            post_commit_actions=post_commit_actions,
        )
