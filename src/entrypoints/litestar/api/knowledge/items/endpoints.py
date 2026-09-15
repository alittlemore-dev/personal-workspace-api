from datetime import datetime
from typing import Annotated

from dishka import FromDishka
from litestar import Controller, Request, delete, get, post, put, status_codes

from core.knowledge.items.use_cases import KnowledgeTagsUseCase
from entrypoints.litestar.api.knowledge.items.schemas import (
    KnowledgeTagRequestSchema,
    KnowledgeTagResponseSchema,
    KnowledgeTagsResponseSchema,
)
from entrypoints.litestar.api.parameters import (
    KnowledgeTagIdPath,
    SearchQueryFilter,
    api_json_body,
)
from infra.config.constants import constants


class KnowledgeTagsApiController(Controller):
    path = "/knowledge/tags"
    tags = ["knowledge tags"]
    include_in_schema = False
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
    )
    async def list_tags(
        self,
        request: Request,
        use_case: FromDishka[KnowledgeTagsUseCase],
        search_query: SearchQueryFilter = None,
    ) -> KnowledgeTagsResponseSchema:
        return KnowledgeTagsResponseSchema.from_domain_schema(
            schemas=await use_case.list_tags(
                author_username=request.user.username,
                search_query=search_query,
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
        request: Request,
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
    )
    async def update_tag(
        self,
        tag_id: KnowledgeTagIdPath,
        data: Annotated[
            KnowledgeTagRequestSchema,
            api_json_body(
                title="Knowledge tag request",
                description="Replacement tag name.",
                examples=({"name": "Команда"},),
            ),
        ],
        request: Request,
        use_case: FromDishka[KnowledgeTagsUseCase],
        current_datetime: FromDishka[datetime],
    ) -> KnowledgeTagResponseSchema:
        return KnowledgeTagResponseSchema.from_domain_schema(
            schema=await use_case.update_tag(
                tag_id=tag_id,
                params=data.to_update_schema(),
                author_username=request.user.username,
                current_datetime=current_datetime,
            ),
        )

    @delete(
        "/{tag_id:str}",
        description="Delete an unused author-scoped knowledge tag.",
        name="knowledge-tags-delete-api-handler",
        status_code=status_codes.HTTP_204_NO_CONTENT,
    )
    async def delete_tag(
        self,
        tag_id: KnowledgeTagIdPath,
        request: Request,
        use_case: FromDishka[KnowledgeTagsUseCase],
    ) -> None:
        await use_case.delete_tag(
            tag_id=tag_id,
            author_username=request.user.username,
        )
