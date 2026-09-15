from datetime import UTC, datetime
from typing import Annotated, Self, cast

from pydantic import Field, model_validator

from core.knowledge.dates.schemas import (
    KnowledgeDate,
    KnowledgeDateCreateParams,
    KnowledgeDateReference,
    KnowledgeDatesPage,
    KnowledgeDateSummary,
    KnowledgeDateUpdateParams,
    KnowledgeDateValue,
    RelatedPerson,
)
from entrypoints.litestar.api.knowledge.files.schemas import KnowledgeFileResponseSchema
from entrypoints.litestar.api.knowledge.items.schemas import KnowledgeTagResponseSchema
from entrypoints.litestar.api.schemas import CamelCaseSchema
from entrypoints.litestar.api.validation import KnowledgeDescriptionText, RequiredShortText


class KnowledgeDateValueSchema(CamelCaseSchema):
    day: Annotated[int, Field(title="Day", ge=1, le=31)]
    month: Annotated[int, Field(title="Month", ge=1, le=12)]
    year: Annotated[int | None, Field(title="Optional first year", ge=1, le=9999)]

    @model_validator(mode="after")
    def validate_date(self) -> Self:  # noqa: N804
        value = self.to_domain_schema()
        value.validate(today=datetime.now(tz=UTC).date())
        return self

    def to_domain_schema(self) -> KnowledgeDateValue:
        return KnowledgeDateValue(day=self.day, month=self.month, year=self.year)

    @classmethod
    def from_domain_schema(cls, *, schema: KnowledgeDateValue) -> Self:
        return cast(
            "Self",
            cls.model_construct(day=schema.day, month=schema.month, year=schema.year),
        )


class RelatedPersonResponseSchema(CamelCaseSchema):
    id: Annotated[str, Field(title="Identifier")]
    display_name: Annotated[str, Field(title="Display name")]

    @classmethod
    def from_domain_schema(cls, *, schema: RelatedPerson) -> Self:
        return cast(
            "Self",
            cls.model_construct(id=schema.id, display_name=schema.display_name),
        )


class KnowledgeDateReferenceResponseSchema(CamelCaseSchema):
    id: Annotated[str, Field(title="Identifier")]
    display_name: Annotated[str, Field(title="Display name")]
    date: Annotated[KnowledgeDateValueSchema, Field(title="Annual date")]

    @classmethod
    def from_domain_schema(cls, *, schema: KnowledgeDateReference) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                id=schema.id,
                display_name=schema.display_name,
                date=KnowledgeDateValueSchema.from_domain_schema(schema=schema.date),
            ),
        )


class KnowledgeDateCreateRequestSchema(CamelCaseSchema):
    display_name: Annotated[RequiredShortText, Field(title="Display name")]
    date: Annotated[KnowledgeDateValueSchema, Field(title="Annual date")]

    def to_domain_schema(self, *, author_username: str) -> KnowledgeDateCreateParams:
        return KnowledgeDateCreateParams(
            display_name=self.display_name,
            date=self.date.to_domain_schema(),
            author_username=author_username,
        )


class KnowledgeDateUpdateRequestSchema(CamelCaseSchema):
    display_name: Annotated[RequiredShortText, Field(title="Display name")]
    date: Annotated[KnowledgeDateValueSchema, Field(title="Annual date")]
    description: Annotated[KnowledgeDescriptionText, Field(title="Markdown description")]
    tag_ids: Annotated[list[str], Field(title="Tag identifiers")]
    person_ids: Annotated[list[str], Field(title="Related person identifiers")]

    def to_domain_schema(self) -> KnowledgeDateUpdateParams:
        return KnowledgeDateUpdateParams(
            display_name=self.display_name,
            date=self.date.to_domain_schema(),
            description=self.description,
            tag_ids=list(self.tag_ids),
            person_ids=list(self.person_ids),
        )


class KnowledgeDateSummaryResponseSchema(CamelCaseSchema):
    id: Annotated[str, Field(title="Identifier")]
    display_name: Annotated[str, Field(title="Display name")]
    date: Annotated[KnowledgeDateValueSchema, Field(title="Annual date")]
    related_people: Annotated[list[RelatedPersonResponseSchema], Field(title="Related people")]
    tags: Annotated[list[KnowledgeTagResponseSchema], Field(title="Tags")]
    created_at: Annotated[str, Field(title="Created at")]
    updated_at: Annotated[str, Field(title="Updated at")]

    @classmethod
    def from_domain_schema(cls, *, schema: KnowledgeDateSummary) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                id=schema.id,
                display_name=schema.display_name,
                date=KnowledgeDateValueSchema.from_domain_schema(schema=schema.date),
                related_people=[
                    RelatedPersonResponseSchema.from_domain_schema(schema=person)
                    for person in schema.related_people
                ],
                tags=[
                    KnowledgeTagResponseSchema.from_domain_schema(schema=tag) for tag in schema.tags
                ],
                created_at=schema.created_at.isoformat(),
                updated_at=schema.updated_at.isoformat(),
            ),
        )


class KnowledgeDatesResponseSchema(CamelCaseSchema):
    total_count: Annotated[int, Field(title="Total count")]
    total_pages: Annotated[int, Field(title="Total pages")]
    dates: Annotated[list[KnowledgeDateSummaryResponseSchema], Field(title="Dates")]

    @classmethod
    def from_domain_schema(cls, *, schema: KnowledgeDatesPage) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                total_count=schema.total_count,
                total_pages=schema.total_pages,
                dates=[
                    KnowledgeDateSummaryResponseSchema.from_domain_schema(schema=value)
                    for value in schema.values
                ],
            ),
        )


class KnowledgeDateResponseSchema(CamelCaseSchema):
    id: Annotated[str, Field(title="Identifier")]
    display_name: Annotated[str, Field(title="Display name")]
    date: Annotated[KnowledgeDateValueSchema, Field(title="Annual date")]
    description: Annotated[str, Field(title="Markdown description")]
    tags: Annotated[list[KnowledgeTagResponseSchema], Field(title="Tags")]
    related_people: Annotated[list[RelatedPersonResponseSchema], Field(title="Related people")]
    attachments: Annotated[list[KnowledgeFileResponseSchema], Field(title="Attachments")]
    created_at: Annotated[str, Field(title="Created at")]
    updated_at: Annotated[str, Field(title="Updated at")]

    @classmethod
    def from_domain_schema(cls, *, schema: KnowledgeDate) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                id=schema.item.id,
                display_name=schema.item.display_name,
                date=KnowledgeDateValueSchema.from_domain_schema(schema=schema.details.date),
                description=schema.item.description,
                tags=[
                    KnowledgeTagResponseSchema.from_domain_schema(schema=tag)
                    for tag in schema.item.tags
                ],
                related_people=[
                    RelatedPersonResponseSchema.from_domain_schema(schema=person)
                    for person in schema.related_people
                ],
                attachments=[
                    KnowledgeFileResponseSchema.from_domain_schema(schema=file)
                    for file in schema.attachments
                ],
                created_at=schema.item.created_at.isoformat(),
                updated_at=schema.item.updated_at.isoformat(),
            ),
        )
