from typing import Annotated, Self, cast

from pydantic import Field

from core.knowledge.items.schemas import (
    KnowledgeTag,
    KnowledgeTagCreateParams,
    KnowledgeTagUpdateParams,
)
from entrypoints.litestar.api.schemas import CamelCaseSchema
from entrypoints.litestar.api.validation import RequiredShortText


class KnowledgeTagResponseSchema(CamelCaseSchema):
    id: Annotated[str, Field(title="Identifier")]
    name: Annotated[str, Field(title="Name")]
    created_at: Annotated[str, Field(title="Created at")]
    updated_at: Annotated[str, Field(title="Updated at")]

    @classmethod
    def from_domain_schema(cls, *, schema: KnowledgeTag) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                id=schema.id,
                name=schema.name,
                created_at=schema.created_at.isoformat(),
                updated_at=schema.updated_at.isoformat(),
            ),
        )


class KnowledgeTagsResponseSchema(CamelCaseSchema):
    tags: Annotated[list[KnowledgeTagResponseSchema], Field(title="Tags")]

    @classmethod
    def from_domain_schema(cls, *, schemas: list[KnowledgeTag]) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                tags=[
                    KnowledgeTagResponseSchema.from_domain_schema(schema=schema)
                    for schema in schemas
                ],
            ),
        )


class KnowledgeTagRequestSchema(CamelCaseSchema):
    name: Annotated[RequiredShortText, Field(title="Name")]

    def to_create_schema(self, *, author_username: str) -> KnowledgeTagCreateParams:
        return KnowledgeTagCreateParams(name=self.name, author_username=author_username)

    def to_update_schema(self) -> KnowledgeTagUpdateParams:
        return KnowledgeTagUpdateParams(name=self.name)
