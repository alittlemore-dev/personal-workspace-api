from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from math import ceil
from typing import Self

from core.knowledge.dates.schemas import KnowledgeDateReference
from core.knowledge.exceptions import InvalidKnowledgeDataError
from core.knowledge.files.schemas import KnowledgeFile
from core.knowledge.items.schemas import KnowledgeItem, KnowledgeTag
from core.knowledge.people.enums import (
    PersonListSort,
    PersonRelationshipDirection,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonBirthday:
    day: int
    month: int
    year: int | None

    def __post_init__(self) -> None:
        validation_year = self.year if self.year is not None else 2000
        try:
            date(validation_year, self.month, self.day)
        except ValueError as error:
            raise InvalidKnowledgeDataError from error

    def validate(self, *, today: date) -> None:
        if self.year is not None and date(self.year, self.month, self.day) > today:
            raise InvalidKnowledgeDataError


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonDetails:
    item_id: str
    last_name: str
    first_name: str
    middle_name: str
    email: str
    phone: str
    telegram: str
    birthday: PersonBirthday | None

    def __post_init__(self) -> None:
        if not self.last_name.strip() or not self.first_name.strip():
            raise InvalidKnowledgeDataError

    @property
    def display_name(self) -> str:
        return " ".join(
            value.strip()
            for value in (self.last_name, self.first_name, self.middle_name)
            if value.strip()
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonRelationshipType:
    id: str
    author_username: str
    is_symmetric: bool
    forward_name: str
    reverse_name: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.forward_name.strip():
            raise InvalidKnowledgeDataError
        if self.is_symmetric and self.reverse_name != self.forward_name:
            raise InvalidKnowledgeDataError
        if not self.is_symmetric and not self.reverse_name.strip():
            raise InvalidKnowledgeDataError


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonRelationship:
    id: str
    author_username: str
    source_person_id: str
    target_person_id: str
    relationship_type: PersonRelationshipType
    note: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.source_person_id == self.target_person_id:
            raise InvalidKnowledgeDataError

    def direction_for(self, *, person_id: str) -> PersonRelationshipDirection:
        if person_id == self.source_person_id:
            return PersonRelationshipDirection.FORWARD
        if person_id == self.target_person_id:
            return PersonRelationshipDirection.REVERSE
        raise InvalidKnowledgeDataError

    def related_person_id_for(self, *, person_id: str) -> str:
        if person_id == self.source_person_id:
            return self.target_person_id
        if person_id == self.target_person_id:
            return self.source_person_id
        raise InvalidKnowledgeDataError

    def label_for(self, *, person_id: str) -> str:
        if self.relationship_type.is_symmetric:
            self.direction_for(person_id=person_id)
            return self.relationship_type.forward_name
        if self.direction_for(person_id=person_id) == PersonRelationshipDirection.FORWARD:
            return self.relationship_type.forward_name
        return self.relationship_type.reverse_name


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonRelationshipView:
    id: str
    related_person_id: str
    related_person_display_name: str
    relationship_type: PersonRelationshipType
    direction: PersonRelationshipDirection
    label: str
    note: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class Person:
    item: KnowledgeItem
    details: PersonDetails
    relationships: list[PersonRelationshipView]
    related_dates: list[KnowledgeDateReference]
    photo: KnowledgeFile | None
    attachments: list[KnowledgeFile]


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonSummary:
    id: str
    display_name: str
    email: str
    phone: str
    telegram: str
    birthday: PersonBirthday | None
    tags: list[KnowledgeTag]
    photo: KnowledgeFile | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class PeoplePage:
    values: list[PersonSummary]
    total_count: int
    total_pages: int

    @classmethod
    def from_values(
        cls,
        *,
        values: list[PersonSummary],
        total_count: int,
        page_size: int,
    ) -> Self:
        return cls(
            values=values,
            total_count=total_count,
            total_pages=ceil(total_count / page_size) if total_count > 0 else 0,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonFilters:
    page: int
    page_size: int
    sort: PersonListSort
    search_query: str | None
    tag_ids: tuple[str, ...]
    author_username: str

    @property
    def limit(self) -> int:
        return self.page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonQuickCreateParams:
    first_name: str
    last_name: str
    author_username: str

    def to_details(self, *, item_id: str) -> PersonDetails:
        return PersonDetails(
            item_id=item_id,
            last_name=self.last_name.strip(),
            first_name=self.first_name.strip(),
            middle_name="",
            email="",
            phone="",
            telegram="",
            birthday=None,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonRelationshipCreateParams:
    related_person_id: str
    relationship_type_id: str
    direction: PersonRelationshipDirection
    note: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonRelationshipUpdateParams:
    id: str
    related_person_id: str
    relationship_type_id: str
    direction: PersonRelationshipDirection
    note: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonRelationshipChanges:
    create: list[PersonRelationshipCreateParams]
    update: list[PersonRelationshipUpdateParams]
    delete_ids: list[str]


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonUpdateParams:
    last_name: str
    first_name: str
    middle_name: str
    email: str
    phone: str
    telegram: str
    birthday: PersonBirthday | None
    description: str
    tag_ids: list[str]
    relationship_changes: PersonRelationshipChanges

    def to_details(self, *, item_id: str) -> PersonDetails:
        return PersonDetails(
            item_id=item_id,
            last_name=self.last_name.strip(),
            first_name=self.first_name.strip(),
            middle_name=self.middle_name.strip(),
            email=self.email.strip(),
            phone=self.phone.strip(),
            telegram=self.telegram.strip(),
            birthday=self.birthday,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonRelationshipTypeCreateParams:
    author_username: str
    is_symmetric: bool
    forward_name: str
    reverse_name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonRelationshipTypeUpdateParams:
    is_symmetric: bool
    forward_name: str
    reverse_name: str


def birthday_max_day(*, month: int, year: int | None) -> int:
    return monthrange(year if year is not None else 2000, month)[1]
