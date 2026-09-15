from datetime import UTC, datetime
from typing import Annotated, Self, cast

from pydantic import Field, model_validator

from core.knowledge.people.enums import PersonRelationshipDirection
from core.knowledge.people.schemas import (
    PeoplePage,
    Person,
    PersonBirthday,
    PersonQuickCreateParams,
    PersonRelationshipChanges,
    PersonRelationshipCreateParams,
    PersonRelationshipType,
    PersonRelationshipTypeCreateParams,
    PersonRelationshipTypeUpdateParams,
    PersonRelationshipUpdateParams,
    PersonRelationshipView,
    PersonSummary,
    PersonUpdateParams,
)
from entrypoints.litestar.api.knowledge.dates.schemas import (
    KnowledgeDateReferenceResponseSchema,
)
from entrypoints.litestar.api.knowledge.files.schemas import KnowledgeFileResponseSchema
from entrypoints.litestar.api.knowledge.items.schemas import KnowledgeTagResponseSchema
from entrypoints.litestar.api.schemas import CamelCaseSchema
from entrypoints.litestar.api.validation import (
    BlankableEmailString,
    KnowledgeDescriptionText,
    KnowledgeRelationshipNoteText,
    RequiredShortText,
    ShortText,
)


class PersonBirthdaySchema(CamelCaseSchema):
    day: Annotated[int, Field(title="Day", ge=1, le=31)]
    month: Annotated[int, Field(title="Month", ge=1, le=12)]
    year: Annotated[int | None, Field(title="Optional year", ge=1, le=9999)]

    @model_validator(mode="after")
    def validate_date(self) -> Self:  # noqa: N804
        birthday = self.to_domain_schema()
        birthday.validate(today=datetime.now(tz=UTC).date())
        return self

    def to_domain_schema(self) -> PersonBirthday:
        return PersonBirthday(day=self.day, month=self.month, year=self.year)

    @classmethod
    def from_domain_schema(cls, *, schema: PersonBirthday) -> Self:
        return cast(
            "Self",
            cls.model_construct(day=schema.day, month=schema.month, year=schema.year),
        )


class PersonRelationshipTypeResponseSchema(CamelCaseSchema):
    id: Annotated[str, Field(title="Identifier")]
    is_symmetric: Annotated[bool, Field(title="Symmetric")]
    forward_name: Annotated[str, Field(title="Forward label")]
    reverse_name: Annotated[str, Field(title="Reverse label")]
    created_at: Annotated[str, Field(title="Created at")]
    updated_at: Annotated[str, Field(title="Updated at")]

    @classmethod
    def from_domain_schema(cls, *, schema: PersonRelationshipType) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                id=schema.id,
                is_symmetric=schema.is_symmetric,
                forward_name=schema.forward_name,
                reverse_name=schema.reverse_name,
                created_at=schema.created_at.isoformat(),
                updated_at=schema.updated_at.isoformat(),
            ),
        )


class PersonRelationshipTypesResponseSchema(CamelCaseSchema):
    relationship_types: Annotated[
        list[PersonRelationshipTypeResponseSchema],
        Field(title="Relationship types"),
    ]

    @classmethod
    def from_domain_schema(cls, *, schemas: list[PersonRelationshipType]) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                relationship_types=[
                    PersonRelationshipTypeResponseSchema.from_domain_schema(schema=schema)
                    for schema in schemas
                ],
            ),
        )


class PersonRelationshipTypeRequestSchema(CamelCaseSchema):
    is_symmetric: Annotated[bool, Field(title="Symmetric")]
    forward_name: Annotated[RequiredShortText, Field(title="Forward label")]
    reverse_name: Annotated[ShortText, Field(title="Reverse label")]

    @model_validator(mode="after")
    def validate_names(self) -> Self:  # noqa: N804
        reverse_name = self.forward_name if self.is_symmetric else self.reverse_name
        PersonRelationshipType(
            id="validation",
            author_username="validation",
            is_symmetric=self.is_symmetric,
            forward_name=self.forward_name,
            reverse_name=reverse_name,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        return self

    def to_create_schema(
        self,
        *,
        author_username: str,
    ) -> PersonRelationshipTypeCreateParams:
        return PersonRelationshipTypeCreateParams(
            author_username=author_username,
            is_symmetric=self.is_symmetric,
            forward_name=self.forward_name,
            reverse_name=self.forward_name if self.is_symmetric else self.reverse_name,
        )

    def to_update_schema(self) -> PersonRelationshipTypeUpdateParams:
        return PersonRelationshipTypeUpdateParams(
            is_symmetric=self.is_symmetric,
            forward_name=self.forward_name,
            reverse_name=self.forward_name if self.is_symmetric else self.reverse_name,
        )


class PersonRelationshipCreateSchema(CamelCaseSchema):
    related_person_id: Annotated[str, Field(title="Related person identifier")]
    relationship_type_id: Annotated[str, Field(title="Relationship type identifier")]
    direction: Annotated[PersonRelationshipDirection, Field(title="Direction")]
    note: Annotated[KnowledgeRelationshipNoteText, Field(title="Note")]

    def to_domain_schema(self) -> PersonRelationshipCreateParams:
        return PersonRelationshipCreateParams(
            related_person_id=self.related_person_id,
            relationship_type_id=self.relationship_type_id,
            direction=self.direction,
            note=self.note,
        )


class PersonRelationshipUpdateSchema(CamelCaseSchema):
    id: Annotated[str, Field(title="Relationship identifier")]
    related_person_id: Annotated[str, Field(title="Related person identifier")]
    relationship_type_id: Annotated[str, Field(title="Relationship type identifier")]
    direction: Annotated[PersonRelationshipDirection, Field(title="Direction")]
    note: Annotated[KnowledgeRelationshipNoteText, Field(title="Note")]

    def to_domain_schema(self) -> PersonRelationshipUpdateParams:
        return PersonRelationshipUpdateParams(
            id=self.id,
            related_person_id=self.related_person_id,
            relationship_type_id=self.relationship_type_id,
            direction=self.direction,
            note=self.note,
        )


class PersonRelationshipChangesSchema(CamelCaseSchema):
    create: Annotated[list[PersonRelationshipCreateSchema], Field(title="Create")]
    update: Annotated[list[PersonRelationshipUpdateSchema], Field(title="Update")]
    delete_ids: Annotated[list[str], Field(title="Delete identifiers")]

    def to_domain_schema(self) -> PersonRelationshipChanges:
        return PersonRelationshipChanges(
            create=[value.to_domain_schema() for value in self.create],
            update=[value.to_domain_schema() for value in self.update],
            delete_ids=list(self.delete_ids),
        )


class PersonRelationshipResponseSchema(CamelCaseSchema):
    id: Annotated[str, Field(title="Identifier")]
    related_person_id: Annotated[str, Field(title="Related person identifier")]
    related_person_display_name: Annotated[str, Field(title="Related person display name")]
    relationship_type: Annotated[
        PersonRelationshipTypeResponseSchema,
        Field(title="Relationship type"),
    ]
    direction: Annotated[PersonRelationshipDirection, Field(title="Direction")]
    label: Annotated[str, Field(title="Projected label")]
    note: Annotated[str, Field(title="Note")]
    created_at: Annotated[str, Field(title="Created at")]
    updated_at: Annotated[str, Field(title="Updated at")]

    @classmethod
    def from_domain_schema(cls, *, schema: PersonRelationshipView) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                id=schema.id,
                related_person_id=schema.related_person_id,
                related_person_display_name=schema.related_person_display_name,
                relationship_type=PersonRelationshipTypeResponseSchema.from_domain_schema(
                    schema=schema.relationship_type,
                ),
                direction=schema.direction,
                label=schema.label,
                note=schema.note,
                created_at=schema.created_at.isoformat(),
                updated_at=schema.updated_at.isoformat(),
            ),
        )


class PersonQuickCreateRequestSchema(CamelCaseSchema):
    first_name: Annotated[RequiredShortText, Field(title="First name")]
    last_name: Annotated[RequiredShortText, Field(title="Last name")]

    def to_domain_schema(self, *, author_username: str) -> PersonQuickCreateParams:
        return PersonQuickCreateParams(
            first_name=self.first_name,
            last_name=self.last_name,
            author_username=author_username,
        )


class PersonUpdateRequestSchema(CamelCaseSchema):
    last_name: Annotated[RequiredShortText, Field(title="Last name")]
    first_name: Annotated[RequiredShortText, Field(title="First name")]
    middle_name: Annotated[ShortText, Field(title="Middle name")]
    email: Annotated[BlankableEmailString, Field(title="Email")]
    phone: Annotated[str, Field(title="Phone", max_length=64)]
    telegram: Annotated[ShortText, Field(title="Telegram")]
    birthday: Annotated[PersonBirthdaySchema | None, Field(title="Birthday")]
    description: Annotated[KnowledgeDescriptionText, Field(title="Markdown description")]
    tag_ids: Annotated[list[str], Field(title="Tag identifiers")]
    relationship_changes: Annotated[
        PersonRelationshipChangesSchema,
        Field(title="Relationship changes"),
    ]

    def to_domain_schema(self) -> PersonUpdateParams:
        return PersonUpdateParams(
            last_name=self.last_name,
            first_name=self.first_name,
            middle_name=self.middle_name,
            email=self.email,
            phone=self.phone,
            telegram=self.telegram,
            birthday=(self.birthday.to_domain_schema() if self.birthday is not None else None),
            description=self.description,
            tag_ids=list(self.tag_ids),
            relationship_changes=self.relationship_changes.to_domain_schema(),
        )


class PersonSummaryResponseSchema(CamelCaseSchema):
    id: Annotated[str, Field(title="Identifier")]
    display_name: Annotated[str, Field(title="Display name")]
    email: Annotated[str, Field(title="Email")]
    phone: Annotated[str, Field(title="Phone")]
    telegram: Annotated[str, Field(title="Telegram")]
    birthday: Annotated[PersonBirthdaySchema | None, Field(title="Birthday")]
    tags: Annotated[list[KnowledgeTagResponseSchema], Field(title="Tags")]
    photo: Annotated[KnowledgeFileResponseSchema | None, Field(title="Photo")]
    created_at: Annotated[str, Field(title="Created at")]
    updated_at: Annotated[str, Field(title="Updated at")]

    @classmethod
    def from_domain_schema(cls, *, schema: PersonSummary) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                id=schema.id,
                display_name=schema.display_name,
                email=schema.email,
                phone=schema.phone,
                telegram=schema.telegram,
                birthday=(
                    PersonBirthdaySchema.from_domain_schema(schema=schema.birthday)
                    if schema.birthday is not None
                    else None
                ),
                tags=[
                    KnowledgeTagResponseSchema.from_domain_schema(schema=tag) for tag in schema.tags
                ],
                photo=(
                    KnowledgeFileResponseSchema.from_domain_schema(schema=schema.photo)
                    if schema.photo is not None
                    else None
                ),
                created_at=schema.created_at.isoformat(),
                updated_at=schema.updated_at.isoformat(),
            ),
        )


class PeopleResponseSchema(CamelCaseSchema):
    total_count: Annotated[int, Field(title="Total count")]
    total_pages: Annotated[int, Field(title="Total pages")]
    people: Annotated[list[PersonSummaryResponseSchema], Field(title="People")]

    @classmethod
    def from_domain_schema(cls, *, schema: PeoplePage) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                total_count=schema.total_count,
                total_pages=schema.total_pages,
                people=[
                    PersonSummaryResponseSchema.from_domain_schema(schema=person)
                    for person in schema.values
                ],
            ),
        )


class PersonResponseSchema(CamelCaseSchema):
    id: Annotated[str, Field(title="Identifier")]
    display_name: Annotated[str, Field(title="Display name")]
    last_name: Annotated[str, Field(title="Last name")]
    first_name: Annotated[str, Field(title="First name")]
    middle_name: Annotated[str, Field(title="Middle name")]
    email: Annotated[str, Field(title="Email")]
    phone: Annotated[str, Field(title="Phone")]
    telegram: Annotated[str, Field(title="Telegram")]
    birthday: Annotated[PersonBirthdaySchema | None, Field(title="Birthday")]
    description: Annotated[str, Field(title="Markdown description")]
    tags: Annotated[list[KnowledgeTagResponseSchema], Field(title="Tags")]
    relationships: Annotated[
        list[PersonRelationshipResponseSchema],
        Field(title="Relationships"),
    ]
    related_dates: Annotated[
        list[KnowledgeDateReferenceResponseSchema],
        Field(title="Related memorable dates"),
    ]
    photo: Annotated[KnowledgeFileResponseSchema | None, Field(title="Photo")]
    attachments: Annotated[list[KnowledgeFileResponseSchema], Field(title="Attachments")]
    created_at: Annotated[str, Field(title="Created at")]
    updated_at: Annotated[str, Field(title="Updated at")]

    @classmethod
    def from_domain_schema(cls, *, schema: Person) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                id=schema.item.id,
                display_name=schema.item.display_name,
                last_name=schema.details.last_name,
                first_name=schema.details.first_name,
                middle_name=schema.details.middle_name,
                email=schema.details.email,
                phone=schema.details.phone,
                telegram=schema.details.telegram,
                birthday=(
                    PersonBirthdaySchema.from_domain_schema(schema=schema.details.birthday)
                    if schema.details.birthday is not None
                    else None
                ),
                description=schema.item.description,
                tags=[
                    KnowledgeTagResponseSchema.from_domain_schema(schema=tag)
                    for tag in schema.item.tags
                ],
                relationships=[
                    PersonRelationshipResponseSchema.from_domain_schema(schema=relationship)
                    for relationship in schema.relationships
                ],
                related_dates=[
                    KnowledgeDateReferenceResponseSchema.from_domain_schema(schema=value)
                    for value in schema.related_dates
                ],
                photo=(
                    KnowledgeFileResponseSchema.from_domain_schema(schema=schema.photo)
                    if schema.photo is not None
                    else None
                ),
                attachments=[
                    KnowledgeFileResponseSchema.from_domain_schema(schema=file)
                    for file in schema.attachments
                ],
                created_at=schema.item.created_at.isoformat(),
                updated_at=schema.item.updated_at.isoformat(),
            ),
        )
