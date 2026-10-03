from typing import Annotated

from backend_sdk import Principal
from backend_sdk.integrations.litestar import AuthContext
from dishka import FromDishka
from litestar import Controller, Request, delete, get, post, put, status_codes
from litestar.datastructures import State
from litestar.di import (
    NamedDependency,
    Provide,
)

from core.knowledge.items.schemas import (
    KnowledgeTagTargetParams,
    ListKnowledgeTagsParams,
    UpdateKnowledgeTagParams,
)
from core.knowledge.items.use_cases import KnowledgeTagsUseCase
from entrypoints.litestar.api.knowledge.items.dependencies import (
    provide_delete_tag_params,
    provide_list_tags_params,
    provide_update_tag_params,
)
from entrypoints.litestar.api.knowledge.items.schemas import (
    KnowledgeTagRequestSchema,
    KnowledgeTagResponseSchema,
    KnowledgeTagsResponseSchema,
)
from entrypoints.litestar.api.parameters import api_json_body
from infra.config.constants import constants


class KnowledgeTagsApiController(Controller):
    path = "/knowledge/tags"
    tags = ["knowledge tags"]
    response_headers = {
        constants.knowledge_files.cache_control_header_name: (
            constants.knowledge_files.no_store_header_value
        ),
    }

    @get(
        "",
        description="List or search current author's knowledge tags.",
        name="knowledge-tags-list-api-handler",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_list_tags_params, sync_to_thread=False)},
    )
    async def list_tags(
        self,
        use_case: FromDishka[KnowledgeTagsUseCase],
        params: NamedDependency[ListKnowledgeTagsParams],
    ) -> KnowledgeTagsResponseSchema:
        return KnowledgeTagsResponseSchema.from_domain_schema(
            schemas=await use_case.list_tags(
                params=params,
            ),
        )

    @post(
        "",
        description="Create an author-scoped knowledge tag.",
        name="knowledge-tags-create-api-handler",
        status_code=status_codes.HTTP_201_CREATED,
    )
    async def create_tag(
        self,
        data: Annotated[
            KnowledgeTagRequestSchema,
            api_json_body(
                title="Knowledge tag request",
                description="Author-scoped tag name.",
                examples=({"name": "Работа"},),
            ),
        ],
        request: Request[Principal, AuthContext, State],
        use_case: FromDishka[KnowledgeTagsUseCase],
    ) -> KnowledgeTagResponseSchema:
        return KnowledgeTagResponseSchema.from_domain_schema(
            schema=await use_case.create_tag(
                params=data.to_create_schema(author_username=request.user.username),
            ),
        )

    @put(
        "/{tag_id:str}",
        description="Rename an author-scoped knowledge tag.",
        name="knowledge-tags-update-api-handler",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_update_tag_params)},
    )
    async def update_tag(
        self,
        use_case: FromDishka[KnowledgeTagsUseCase],
        params: NamedDependency[UpdateKnowledgeTagParams],
    ) -> KnowledgeTagResponseSchema:
        return KnowledgeTagResponseSchema.from_domain_schema(
            schema=await use_case.update_tag(
                params=params,
            ),
        )

    @delete(
        "/{tag_id:str}",
        description="Delete an unused author-scoped knowledge tag.",
        name="knowledge-tags-delete-api-handler",
        status_code=status_codes.HTTP_204_NO_CONTENT,
        dependencies={"params": Provide(provide_delete_tag_params, sync_to_thread=False)},
    )
    async def delete_tag(
        self,
        use_case: FromDishka[KnowledgeTagsUseCase],
        params: NamedDependency[KnowledgeTagTargetParams],
    ) -> None:
        await use_case.delete_tag(
            params=params,
        )
