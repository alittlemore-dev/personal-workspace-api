from datetime import datetime
from typing import Annotated

from backend_sdk import Principal
from backend_sdk.integrations.litestar import AuthContext
from dishka import FromDishka
from dishka.integrations.litestar import inject
from litestar import Request
from litestar.datastructures import State

from core.knowledge.people.schemas import (
    CreatePersonRelationshipTypeParams,
    DeletePersonParams,
    PersonFilters,
    PersonRelationshipTypeTargetParams,
    PersonTargetParams,
    UpdatePersonParams,
    UpdatePersonRelationshipTypeParams,
)
from entrypoints.litestar.api.knowledge.people.schemas import (
    PersonRelationshipTypeRequestSchema,
    PersonUpdateRequestSchema,
)
from entrypoints.litestar.api.parameters import (
    KnowledgeTagIdsQuery,
    PageQuery,
    PageSizeQuery,
    PersonIdPath,
    PersonListSortQuery,
    PersonRelationshipTypeIdPath,
    SearchQueryFilter,
    api_json_body,
)


def provide_person_filters(  # noqa: PLR0913
    request: Request[Principal, AuthContext, State],
    page: PageQuery,
    page_size: PageSizeQuery,
    sort: PersonListSortQuery,
    search_query: SearchQueryFilter = None,
    tag_ids: KnowledgeTagIdsQuery = None,
) -> PersonFilters:
    normalized_search_query = (
        search_query.strip() if search_query is not None and search_query.strip() else None
    )
    return PersonFilters(
        page=page,
        page_size=page_size,
        sort=sort,
        search_query=normalized_search_query,
        tag_ids=tuple(dict.fromkeys(tag_ids or [])),
        author_username=request.user.username,
    )


def provide_get_person_params(
    person_id: PersonIdPath,
    request: Request[Principal, AuthContext, State],
) -> PersonTargetParams:
    return PersonTargetParams(
        person_id=person_id,
        author_username=request.user.username,
    )


@inject
async def provide_update_person_params(
    person_id: PersonIdPath,
    data: Annotated[
        PersonUpdateRequestSchema,
        api_json_body(
            title="Person update request",
            description="Complete editable person payload.",
            examples=(
                {
                    "lastName": "Иванов",
                    "firstName": "Иван",
                    "middleName": "",
                    "email": "",
                    "phone": "",
                    "telegram": "",
                    "birthday": None,
                    "description": "",
                    "tagIds": [],
                    "relationshipChanges": {
                        "create": [],
                        "update": [],
                        "deleteIds": [],
                    },
                },
            ),
        ),
    ],
    request: Request[Principal, AuthContext, State],
    current_datetime: FromDishka[datetime],
) -> UpdatePersonParams:
    return UpdatePersonParams(
        person_id=person_id,
        data=data.to_domain_schema(),
        author_username=request.user.username,
        current_datetime=current_datetime,
    )


@inject
async def provide_delete_person_params(
    person_id: PersonIdPath,
    request: Request[Principal, AuthContext, State],
    current_datetime: FromDishka[datetime],
) -> DeletePersonParams:
    return DeletePersonParams(
        person_id=person_id,
        author_username=request.user.username,
        current_datetime=current_datetime,
    )


@inject
async def provide_create_relationship_type_params(
    data: Annotated[
        PersonRelationshipTypeRequestSchema,
        api_json_body(
            title="Relationship type request",
            description="Symmetric or directional labels.",
            examples=(
                {
                    "isSymmetric": False,
                    "forwardName": "руководитель",
                    "reverseName": "подчинённый",
                },
            ),
        ),
    ],
    request: Request[Principal, AuthContext, State],
    current_datetime: FromDishka[datetime],
) -> CreatePersonRelationshipTypeParams:
    return CreatePersonRelationshipTypeParams(
        data=data.to_create_schema(author_username=request.user.username),
        current_datetime=current_datetime,
    )


@inject
async def provide_update_relationship_type_params(
    relationship_type_id: PersonRelationshipTypeIdPath,
    data: Annotated[
        PersonRelationshipTypeRequestSchema,
        api_json_body(
            title="Relationship type request",
            description="Complete relationship type payload.",
            examples=(
                {
                    "isSymmetric": True,
                    "forwardName": "друг",
                    "reverseName": "",
                },
            ),
        ),
    ],
    request: Request[Principal, AuthContext, State],
    current_datetime: FromDishka[datetime],
) -> UpdatePersonRelationshipTypeParams:
    return UpdatePersonRelationshipTypeParams(
        relationship_type_id=relationship_type_id,
        data=data.to_update_schema(),
        author_username=request.user.username,
        current_datetime=current_datetime,
    )


def provide_delete_relationship_type_params(
    relationship_type_id: PersonRelationshipTypeIdPath,
    request: Request[Principal, AuthContext, State],
) -> PersonRelationshipTypeTargetParams:
    return PersonRelationshipTypeTargetParams(
        relationship_type_id=relationship_type_id,
        author_username=request.user.username,
    )
