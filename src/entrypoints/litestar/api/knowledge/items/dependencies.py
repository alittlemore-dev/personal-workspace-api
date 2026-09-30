from datetime import datetime
from typing import Annotated

from backend_sdk import Principal
from backend_sdk.integrations.litestar import AuthContext
from dishka import FromDishka
from dishka.integrations.litestar import inject
from litestar import Request
from litestar.datastructures import State

from core.knowledge.items.schemas import (
    KnowledgeTagTargetParams,
    ListKnowledgeTagsParams,
    UpdateKnowledgeTagParams,
)
from entrypoints.litestar.api.knowledge.items.schemas import KnowledgeTagRequestSchema
from entrypoints.litestar.api.parameters import (
    KnowledgeTagIdPath,
    SearchQueryFilter,
    api_json_body,
)


def provide_list_tags_params(
    request: Request[Principal, AuthContext, State],
    search_query: SearchQueryFilter = None,
) -> ListKnowledgeTagsParams:
    return ListKnowledgeTagsParams(
        author_username=request.user.username,
        search_query=search_query,
    )


@inject
async def provide_update_tag_params(
    tag_id: KnowledgeTagIdPath,
    data: Annotated[
        KnowledgeTagRequestSchema,
        api_json_body(
            title="Knowledge tag request",
            description="Replacement tag name.",
            examples=({"name": "Команда"},),
        ),
    ],
    request: Request[Principal, AuthContext, State],
    current_datetime: FromDishka[datetime],
) -> UpdateKnowledgeTagParams:
    return UpdateKnowledgeTagParams(
        tag_id=tag_id,
        data=data.to_update_schema(),
        author_username=request.user.username,
        current_datetime=current_datetime,
    )


def provide_delete_tag_params(
    tag_id: KnowledgeTagIdPath,
    request: Request[Principal, AuthContext, State],
) -> KnowledgeTagTargetParams:
    return KnowledgeTagTargetParams(
        tag_id=tag_id,
        author_username=request.user.username,
    )
