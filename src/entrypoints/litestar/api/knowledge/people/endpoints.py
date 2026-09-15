from datetime import datetime
from typing import Annotated

from dishka import FromDishka
from litestar import Controller, Request, delete, get, post, put, status_codes
from litestar.di import NamedDependency, Provide

from core.knowledge.files.clients import KnowledgeFileObjectCleaner
from core.knowledge.people.schemas import PersonFilters
from core.knowledge.people.use_cases import (
    PeopleUseCase,
    PersonRelationshipTypesUseCase,
)
from entrypoints.litestar.api.knowledge.files.post_commit import (
    register_knowledge_object_cleanup,
)
from entrypoints.litestar.api.knowledge.people.dependencies import provide_person_filters
from entrypoints.litestar.api.knowledge.people.schemas import (
    PeopleResponseSchema,
    PersonQuickCreateRequestSchema,
    PersonRelationshipTypeRequestSchema,
    PersonRelationshipTypeResponseSchema,
    PersonRelationshipTypesResponseSchema,
    PersonResponseSchema,
    PersonUpdateRequestSchema,
)
from entrypoints.litestar.api.parameters import (
    PersonIdPath,
    PersonRelationshipTypeIdPath,
    api_json_body,
)
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
            PersonQuickCreateRequestSchema,
            api_json_body(
                title="Person quick-create request",
                description="Required name parts for a new private person.",
                examples=({"firstName": "Иван", "lastName": "Иванов"},),
            ),
        ],
        request: Request,
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
    )
    async def get_person(
        self,
        person_id: PersonIdPath,
        request: Request,
        use_case: FromDishka[PeopleUseCase],
    ) -> PersonResponseSchema:
        return PersonResponseSchema.from_domain_schema(
            schema=await use_case.get_person(
                person_id=person_id,
                author_username=request.user.username,
            ),
        )

    @put(
        "/{person_id:str}",
        description="Replace editable private person data and apply relationship commands.",
        name="knowledge-people-update-api-handler",
        status_code=status_codes.HTTP_200_OK,
    )
    async def update_person(
        self,
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
        request: Request,
        use_case: FromDishka[PeopleUseCase],
        current_datetime: FromDishka[datetime],
    ) -> PersonResponseSchema:
        return PersonResponseSchema.from_domain_schema(
            schema=await use_case.update_person(
                person_id=person_id,
                params=data.to_domain_schema(),
                author_username=request.user.username,
                current_datetime=current_datetime,
            ),
        )

    @delete(
        "/{person_id:str}",
        description="Permanently delete a private person.",
        name="knowledge-people-delete-api-handler",
        status_code=status_codes.HTTP_204_NO_CONTENT,
    )
    async def delete_person(  # noqa: PLR0913
        self,
        person_id: PersonIdPath,
        request: Request,
        use_case: FromDishka[PeopleUseCase],
        object_cleaner: FromDishka[KnowledgeFileObjectCleaner],
        post_commit_actions: FromDishka[PostCommitActions],
        current_datetime: FromDishka[datetime],
    ) -> None:
        object_names = await use_case.delete_person(
            person_id=person_id,
            author_username=request.user.username,
            current_datetime=current_datetime,
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
        request: Request,
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
    )
    async def create_relationship_type(
        self,
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
        request: Request,
        use_case: FromDishka[PersonRelationshipTypesUseCase],
        current_datetime: FromDishka[datetime],
    ) -> PersonRelationshipTypeResponseSchema:
        return PersonRelationshipTypeResponseSchema.from_domain_schema(
            schema=await use_case.create_relationship_type(
                params=data.to_create_schema(author_username=request.user.username),
                current_datetime=current_datetime,
            ),
        )

    @put(
        "/relationship-types/{relationship_type_id:str}",
        description="Update an author-scoped person relationship type.",
        name="knowledge-relationship-types-update-api-handler",
        status_code=status_codes.HTTP_200_OK,
    )
    async def update_relationship_type(
        self,
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
        request: Request,
        use_case: FromDishka[PersonRelationshipTypesUseCase],
        current_datetime: FromDishka[datetime],
    ) -> PersonRelationshipTypeResponseSchema:
        return PersonRelationshipTypeResponseSchema.from_domain_schema(
            schema=await use_case.update_relationship_type(
                relationship_type_id=relationship_type_id,
                params=data.to_update_schema(),
                author_username=request.user.username,
                current_datetime=current_datetime,
            ),
        )

    @delete(
        "/relationship-types/{relationship_type_id:str}",
        description="Delete an unused author-scoped relationship type.",
        name="knowledge-relationship-types-delete-api-handler",
        status_code=status_codes.HTTP_204_NO_CONTENT,
    )
    async def delete_relationship_type(
        self,
        relationship_type_id: PersonRelationshipTypeIdPath,
        request: Request,
        use_case: FromDishka[PersonRelationshipTypesUseCase],
    ) -> None:
        await use_case.delete_relationship_type(
            relationship_type_id=relationship_type_id,
            author_username=request.user.username,
        )
