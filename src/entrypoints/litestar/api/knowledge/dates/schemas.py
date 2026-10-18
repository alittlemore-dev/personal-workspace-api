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
    day: Annotated[
        int,
        Field(
            title="Day",
            ge=1,
            le=31,
            description=(
                "Day of the month, from 1 to 31; must form a valid date with month and year."
            ),
            examples=[18],
        ),
    ]
    month: Annotated[
        int,
        Field(
            title="Month",
            ge=1,
            le=12,
            description="Calendar month, from 1 to 12.",
            examples=[10],
        ),
    ]
    year: Annotated[
        int | None,
        Field(
            title="Optional first year",
            ge=1,
            le=9999,
            description="Original year; null when the year is unknown.",
            examples=[1992],
        ),
    ]

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
    id: Annotated[
        str,
        Field(
            title="Identifier",
            description="Opaque resource identifier; use the value returned by this API.",
            examples=["4e92d4de561f4bc7a3eed227868952db"],
        ),
    ]
    display_name: Annotated[
        str,
        Field(
            title="Display name",
            description="Human-readable display name.",
            examples=["Alex Morgan"],
        ),
    ]

    @classmethod
    def from_domain_schema(cls, *, schema: RelatedPerson) -> Self:
        return cast(
            "Self",
            cls.model_construct(id=schema.id, display_name=schema.display_name),
        )


class KnowledgeDateReferenceResponseSchema(CamelCaseSchema):
    id: Annotated[
        str,
        Field(
            title="Identifier",
            description="Opaque resource identifier; use the value returned by this API.",
            examples=["4e92d4de561f4bc7a3eed227868952db"],
        ),
    ]
    display_name: Annotated[
        str,
        Field(
            title="Display name",
            description="Name of the memorable date.",
            examples=["Wedding anniversary"],
        ),
    ]
    date: Annotated[
        KnowledgeDateValueSchema,
        Field(title="Annual date", description="Date; see the nested schema for its fields."),
    ]

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
    display_name: Annotated[
        RequiredShortText,
        Field(
            title="Display name",
            description="Name of the memorable date.",
            examples=["Wedding anniversary"],
        ),
    ]
    date: Annotated[
        KnowledgeDateValueSchema,
        Field(title="Annual date", description="Date; see the nested schema for its fields."),
    ]

    def to_domain_schema(self, *, author_username: str) -> KnowledgeDateCreateParams:
        return KnowledgeDateCreateParams(
            display_name=self.display_name,
            date=self.date.to_domain_schema(),
            author_username=author_username,
        )


class KnowledgeDateUpdateRequestSchema(CamelCaseSchema):
    display_name: Annotated[
        RequiredShortText,
        Field(
            title="Display name",
            description="Name of the memorable date.",
            examples=["Wedding anniversary"],
        ),
    ]
    date: Annotated[
        KnowledgeDateValueSchema,
        Field(title="Annual date", description="Date; see the nested schema for its fields."),
    ]
    description: Annotated[
        KnowledgeDescriptionText,
        Field(
            title="Markdown description",
            description="Human-readable description.",
            examples=["Designed APIs and reduced request latency by 30%."],
        ),
    ]
    tag_ids: Annotated[
        list[str],
        Field(
            title="Tag identifiers",
            description="Tag identifiers owned by the authenticated user.",
            examples=[["cabe3a7dd502458aa35e3d95d0953eaf"]],
        ),
    ]
    person_ids: Annotated[
        list[str],
        Field(
            title="Related person identifiers",
            description="Identifiers of related people owned by the authenticated user.",
            examples=[["1bb209e394954b71bd78b52d572dd835"]],
        ),
    ]
    notifications_enabled: bool = Field(
        description="Whether notifications are enabled for this person or annual date.",
        examples=[True],
    )

    def to_domain_schema(self) -> KnowledgeDateUpdateParams:
        return KnowledgeDateUpdateParams(
            display_name=self.display_name,
            date=self.date.to_domain_schema(),
            description=self.description,
            tag_ids=list(self.tag_ids),
            person_ids=list(self.person_ids),
            notifications_enabled=self.notifications_enabled,
        )


class KnowledgeDateSummaryResponseSchema(CamelCaseSchema):
    id: Annotated[
        str,
        Field(
            title="Identifier",
            description="Opaque resource identifier; use the value returned by this API.",
            examples=["4e92d4de561f4bc7a3eed227868952db"],
        ),
    ]
    display_name: Annotated[
        str,
        Field(
            title="Display name",
            description="Name of the memorable date.",
            examples=["Wedding anniversary"],
        ),
    ]
    date: Annotated[
        KnowledgeDateValueSchema,
        Field(title="Annual date", description="Date; see the nested schema for its fields."),
    ]
    related_people: Annotated[
        list[RelatedPersonResponseSchema],
        Field(title="Related people", description="Related people returned by this operation."),
    ]
    tags: Annotated[
        list[KnowledgeTagResponseSchema],
        Field(title="Tags", description="Tags returned by this operation."),
    ]
    created_at: Annotated[
        str,
        Field(
            title="Created at",
            description="Creation timestamp in ISO 8601 format.",
            examples=["2026-10-18T09:00:00Z"],
        ),
    ]
    updated_at: Annotated[
        str,
        Field(
            title="Updated at",
            description="Last modification timestamp in ISO 8601 format.",
            examples=["2026-10-18T10:30:00Z"],
        ),
    ]

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
    total_count: Annotated[
        int,
        Field(
            title="Total count",
            description="Total number of matching records before pagination.",
            examples=[42],
        ),
    ]
    total_pages: Annotated[
        int,
        Field(
            title="Total pages",
            description=(
                "Number of pages for the requested pageSize; zero when there are no "
                "matching records."
            ),
            examples=[3],
        ),
    ]
    dates: Annotated[
        list[KnowledgeDateSummaryResponseSchema],
        Field(title="Dates", description="Dates returned by this operation."),
    ]

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
    id: Annotated[
        str,
        Field(
            title="Identifier",
            description="Opaque resource identifier; use the value returned by this API.",
            examples=["4e92d4de561f4bc7a3eed227868952db"],
        ),
    ]
    display_name: Annotated[
        str,
        Field(
            title="Display name",
            description="Name of the memorable date.",
            examples=["Wedding anniversary"],
        ),
    ]
    date: Annotated[
        KnowledgeDateValueSchema,
        Field(title="Annual date", description="Date; see the nested schema for its fields."),
    ]
    description: Annotated[
        str,
        Field(
            title="Markdown description",
            description="Human-readable description.",
            examples=["Designed APIs and reduced request latency by 30%."],
        ),
    ]
    notifications_enabled: bool = Field(
        description="Whether notifications are enabled for this person or annual date.",
        examples=[True],
    )
    tags: Annotated[
        list[KnowledgeTagResponseSchema],
        Field(title="Tags", description="Tags returned by this operation."),
    ]
    related_people: Annotated[
        list[RelatedPersonResponseSchema],
        Field(title="Related people", description="Related people returned by this operation."),
    ]
    attachments: Annotated[
        list[KnowledgeFileResponseSchema],
        Field(title="Attachments", description="Attachments returned by this operation."),
    ]
    created_at: Annotated[
        str,
        Field(
            title="Created at",
            description="Creation timestamp in ISO 8601 format.",
            examples=["2026-10-18T09:00:00Z"],
        ),
    ]
    updated_at: Annotated[
        str,
        Field(
            title="Updated at",
            description="Last modification timestamp in ISO 8601 format.",
            examples=["2026-10-18T10:30:00Z"],
        ),
    ]

    @classmethod
    def from_domain_schema(cls, *, schema: KnowledgeDate) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                id=schema.item.id,
                display_name=schema.item.display_name,
                date=KnowledgeDateValueSchema.from_domain_schema(schema=schema.details.date),
                description=schema.item.description,
                notifications_enabled=schema.details.notifications_enabled,
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
