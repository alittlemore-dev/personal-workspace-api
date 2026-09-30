from datetime import datetime
from typing import Annotated

from backend_sdk import Principal
from backend_sdk.integrations.litestar import AuthContext
from dishka import FromDishka
from dishka.integrations.litestar import inject
from litestar import Request
from litestar.datastructures import State

from core.knowledge.dates.schemas import (
    CreateKnowledgeDateParams,
    DeleteKnowledgeDateParams,
    KnowledgeDateFilters,
    KnowledgeDateTargetParams,
    UpdateKnowledgeDateParams,
)
from entrypoints.litestar.api.knowledge.dates.schemas import (
    KnowledgeDateCreateRequestSchema,
    KnowledgeDateUpdateRequestSchema,
)
from entrypoints.litestar.api.parameters import (
    KnowledgeDateIdPath,
    KnowledgeDateListSortQuery,
    KnowledgeTagIdsQuery,
    PageQuery,
    PageSizeQuery,
    RelatedPersonIdQuery,
    SearchQueryFilter,
    api_json_body,
)


def provide_knowledge_date_filters(  # noqa: PLR0913
    request: Request[Principal, AuthContext, State],
    page: PageQuery,
    page_size: PageSizeQuery,
    sort: KnowledgeDateListSortQuery,
    search_query: SearchQueryFilter = None,
    tag_ids: KnowledgeTagIdsQuery = None,
    related_person_id: RelatedPersonIdQuery = None,
) -> KnowledgeDateFilters:
    normalized_search_query = (
        search_query.strip() if search_query is not None and search_query.strip() else None
    )
    return KnowledgeDateFilters(
        page=page,
        page_size=page_size,
        sort=sort,
        search_query=normalized_search_query,
        tag_ids=tuple(dict.fromkeys(tag_ids or [])),
        related_person_id=related_person_id,
        author_username=request.user.username,
    )


@inject
async def provide_create_date_params(
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
    request: Request[Principal, AuthContext, State],
    current_datetime: FromDishka[datetime],
) -> CreateKnowledgeDateParams:
    return CreateKnowledgeDateParams(
        data=data.to_domain_schema(author_username=request.user.username),
        today=current_datetime.date(),
    )


def provide_get_date_params(
    date_id: KnowledgeDateIdPath,
    request: Request[Principal, AuthContext, State],
) -> KnowledgeDateTargetParams:
    return KnowledgeDateTargetParams(
        date_id=date_id,
        author_username=request.user.username,
    )


@inject
async def provide_update_date_params(
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
    request: Request[Principal, AuthContext, State],
    current_datetime: FromDishka[datetime],
) -> UpdateKnowledgeDateParams:
    return UpdateKnowledgeDateParams(
        date_id=date_id,
        data=data.to_domain_schema(),
        author_username=request.user.username,
        current_datetime=current_datetime,
    )


@inject
async def provide_delete_date_params(
    date_id: KnowledgeDateIdPath,
    request: Request[Principal, AuthContext, State],
    current_datetime: FromDishka[datetime],
) -> DeleteKnowledgeDateParams:
    return DeleteKnowledgeDateParams(
        date_id=date_id,
        author_username=request.user.username,
        current_datetime=current_datetime,
    )
