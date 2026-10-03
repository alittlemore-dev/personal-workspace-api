from dishka import FromDishka
from litestar import Controller, delete, get, post, put, status_codes
from litestar.di import NamedDependency, Provide

from core.knowledge.dates.schemas import (
    CreateKnowledgeDateParams,
    DeleteKnowledgeDateParams,
    KnowledgeDateFilters,
    KnowledgeDateTargetParams,
    UpdateKnowledgeDateParams,
)
from core.knowledge.dates.use_cases import KnowledgeDatesUseCase
from core.knowledge.files.clients import KnowledgeFileObjectCleaner
from entrypoints.litestar.api.knowledge.dates.dependencies import (
    provide_create_date_params,
    provide_delete_date_params,
    provide_get_date_params,
    provide_knowledge_date_filters,
    provide_update_date_params,
)
from entrypoints.litestar.api.knowledge.dates.schemas import (
    KnowledgeDateResponseSchema,
    KnowledgeDatesResponseSchema,
)
from entrypoints.litestar.api.knowledge.files.post_commit import register_knowledge_object_cleanup
from infra.config.constants import constants
from infra.post_commit_actions import PostCommitActions


class KnowledgeDatesApiController(Controller):
    path = "/knowledge/dates"
    tags = ["knowledge dates"]
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
        dependencies={"params": Provide(provide_create_date_params)},
    )
    async def create_date(
        self,
        use_case: FromDishka[KnowledgeDatesUseCase],
        params: NamedDependency[CreateKnowledgeDateParams],
    ) -> KnowledgeDateResponseSchema:
        return KnowledgeDateResponseSchema.from_domain_schema(
            schema=await use_case.create_date(
                params=params,
            ),
        )

    @get(
        "/{date_id:str}",
        description="Get one private memorable date owned by the current author.",
        name="knowledge-dates-detail-api-handler",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_get_date_params, sync_to_thread=False)},
    )
    async def get_date(
        self,
        use_case: FromDishka[KnowledgeDatesUseCase],
        params: NamedDependency[KnowledgeDateTargetParams],
    ) -> KnowledgeDateResponseSchema:
        return KnowledgeDateResponseSchema.from_domain_schema(
            schema=await use_case.get_date(
                params=params,
            ),
        )

    @put(
        "/{date_id:str}",
        description="Replace editable private memorable date data.",
        name="knowledge-dates-update-api-handler",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_update_date_params)},
    )
    async def update_date(
        self,
        use_case: FromDishka[KnowledgeDatesUseCase],
        params: NamedDependency[UpdateKnowledgeDateParams],
    ) -> KnowledgeDateResponseSchema:
        return KnowledgeDateResponseSchema.from_domain_schema(
            schema=await use_case.update_date(
                params=params,
            ),
        )

    @delete(
        "/{date_id:str}",
        description="Permanently delete a private memorable date.",
        name="knowledge-dates-delete-api-handler",
        status_code=status_codes.HTTP_204_NO_CONTENT,
        dependencies={"params": Provide(provide_delete_date_params)},
    )
    async def delete_date(
        self,
        use_case: FromDishka[KnowledgeDatesUseCase],
        object_cleaner: FromDishka[KnowledgeFileObjectCleaner],
        post_commit_actions: FromDishka[PostCommitActions],
        params: NamedDependency[DeleteKnowledgeDateParams],
    ) -> None:
        object_names = await use_case.delete_date(
            params=params,
        )
        register_knowledge_object_cleanup(
            object_names=object_names,
            object_cleaner=object_cleaner,
            post_commit_actions=post_commit_actions,
        )
