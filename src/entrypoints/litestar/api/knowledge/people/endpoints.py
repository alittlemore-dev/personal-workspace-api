from typing import Annotated

from backend_sdk import Principal
from backend_sdk.integrations.litestar import AuthContext
from dishka import FromDishka
from litestar import Controller, Request, delete, get, post, put, status_codes
from litestar.datastructures import State
from litestar.di import NamedDependency, Provide

from core.knowledge.files.clients import KnowledgeFileObjectCleaner
from core.knowledge.people.schemas import (
    CreatePersonRelationshipTypeParams,
    DeletePersonParams,
    PersonFilters,
    PersonRelationshipTypeTargetParams,
    PersonTargetParams,
    UpdatePersonParams,
    UpdatePersonRelationshipTypeParams,
)
from core.knowledge.people.use_cases import (
    PeopleUseCase,
    PersonRelationshipTypesUseCase,
)
from entrypoints.litestar.api.knowledge.files.post_commit import register_knowledge_object_cleanup
from entrypoints.litestar.api.knowledge.people.dependencies import (
    provide_create_relationship_type_params,
    provide_delete_person_params,
    provide_delete_relationship_type_params,
    provide_get_person_params,
    provide_person_filters,
    provide_update_person_params,
    provide_update_relationship_type_params,
)
from entrypoints.litestar.api.knowledge.people.schemas import (
    PeopleResponseSchema,
    PersonCreateRequestSchema,
    PersonRelationshipTypeResponseSchema,
    PersonRelationshipTypesResponseSchema,
    PersonResponseSchema,
)
from entrypoints.litestar.api.parameters import api_json_body
from infra.config.constants import constants
from infra.post_commit_actions import PostCommitActions


class PeopleApiController(Controller):
    path = "/knowledge/people"
    tags = ["knowledge people"]
    include_in_schema = False
    response_headers = {
        constants.knowledge_files.cache_control_header_name: (
            constants.knowledge_files.no_store_header_value
        ),
    }

    @get(
        "",
        description="List private people owned by the current author.",
        name="knowledge-people-list-api-handler",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"filters": Provide(provide_person_filters, sync_to_thread=False)},
    )
    async def list_people(
        self,
        use_case: FromDishka[PeopleUseCase],
        filters: NamedDependency[PersonFilters],
    ) -> PeopleResponseSchema:
        return PeopleResponseSchema.from_domain_schema(
            schema=await use_case.list_people(filters=filters),
        )

    @post(
        "",
        description="Quick-create a private person.",
        name="knowledge-people-create-api-handler",
        status_code=status_codes.HTTP_201_CREATED,
    )
    async def create_person(
        self,
        data: Annotated[
            PersonCreateRequestSchema,
            api_json_body(
                title="Person quick-create request",
                description="Required name parts for a new private person.",
                examples=({"firstName": "Иван", "lastName": "Иванов"},),
            ),
        ],
        request: Request[Principal, AuthContext, State],
        use_case: FromDishka[PeopleUseCase],
    ) -> PersonResponseSchema:
        return PersonResponseSchema.from_domain_schema(
            schema=await use_case.create_person(
                params=data.to_domain_schema(author_username=request.user.username),
            ),
        )

    @get(
        "/{person_id:str}",
        description="Get one private person owned by the current author.",
        name="knowledge-people-detail-api-handler",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_get_person_params, sync_to_thread=False)},
    )
    async def get_person(
        self,
        use_case: FromDishka[PeopleUseCase],
        params: NamedDependency[PersonTargetParams],
    ) -> PersonResponseSchema:
        return PersonResponseSchema.from_domain_schema(
            schema=await use_case.get_person(
                params=params,
            ),
        )

    @put(
        "/{person_id:str}",
        description="Replace editable private person data and apply relationship commands.",
        name="knowledge-people-update-api-handler",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_update_person_params)},
    )
    async def update_person(
        self,
        use_case: FromDishka[PeopleUseCase],
        params: NamedDependency[UpdatePersonParams],
    ) -> PersonResponseSchema:
        return PersonResponseSchema.from_domain_schema(
            schema=await use_case.update_person(
                params=params,
            ),
        )

    @delete(
        "/{person_id:str}",
        description="Permanently delete a private person.",
        name="knowledge-people-delete-api-handler",
        status_code=status_codes.HTTP_204_NO_CONTENT,
        dependencies={"params": Provide(provide_delete_person_params)},
    )
    async def delete_person(
        self,
        use_case: FromDishka[PeopleUseCase],
        object_cleaner: FromDishka[KnowledgeFileObjectCleaner],
        post_commit_actions: FromDishka[PostCommitActions],
        params: NamedDependency[DeletePersonParams],
    ) -> None:
        object_names = await use_case.delete_person(
            params=params,
        )
        register_knowledge_object_cleanup(
            object_names=object_names,
            object_cleaner=object_cleaner,
            post_commit_actions=post_commit_actions,
        )

    @get(
        "/relationship-types",
        description="List author-scoped person relationship types.",
        name="knowledge-relationship-types-list-api-handler",
        status_code=status_codes.HTTP_200_OK,
    )
    async def list_relationship_types(
        self,
        request: Request[Principal, AuthContext, State],
        use_case: FromDishka[PersonRelationshipTypesUseCase],
    ) -> PersonRelationshipTypesResponseSchema:
        return PersonRelationshipTypesResponseSchema.from_domain_schema(
            schemas=await use_case.list_relationship_types(
                author_username=request.user.username,
            ),
        )

    @post(
        "/relationship-types",
        description="Create an author-scoped person relationship type.",
        name="knowledge-relationship-types-create-api-handler",
        status_code=status_codes.HTTP_201_CREATED,
        dependencies={
            "params": Provide(provide_create_relationship_type_params),
        },
    )
    async def create_relationship_type(
        self,
        use_case: FromDishka[PersonRelationshipTypesUseCase],
        params: NamedDependency[CreatePersonRelationshipTypeParams],
    ) -> PersonRelationshipTypeResponseSchema:
        return PersonRelationshipTypeResponseSchema.from_domain_schema(
            schema=await use_case.create_relationship_type(
                params=params,
            ),
        )

    @put(
        "/relationship-types/{relationship_type_id:str}",
        description="Update an author-scoped person relationship type.",
        name="knowledge-relationship-types-update-api-handler",
        status_code=status_codes.HTTP_200_OK,
        dependencies={
            "params": Provide(provide_update_relationship_type_params),
        },
    )
    async def update_relationship_type(
        self,
        use_case: FromDishka[PersonRelationshipTypesUseCase],
        params: NamedDependency[UpdatePersonRelationshipTypeParams],
    ) -> PersonRelationshipTypeResponseSchema:
        return PersonRelationshipTypeResponseSchema.from_domain_schema(
            schema=await use_case.update_relationship_type(
                params=params,
            ),
        )

    @delete(
        "/relationship-types/{relationship_type_id:str}",
        description="Delete an unused author-scoped relationship type.",
        name="knowledge-relationship-types-delete-api-handler",
        status_code=status_codes.HTTP_204_NO_CONTENT,
        dependencies={
            "params": Provide(provide_delete_relationship_type_params, sync_to_thread=False),
        },
    )
    async def delete_relationship_type(
        self,
        use_case: FromDishka[PersonRelationshipTypesUseCase],
        params: NamedDependency[PersonRelationshipTypeTargetParams],
    ) -> None:
        await use_case.delete_relationship_type(
            params=params,
        )
