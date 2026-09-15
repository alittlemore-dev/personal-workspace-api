from dataclasses import dataclass
from datetime import date, datetime
from math import ceil
from typing import Self

from core.knowledge.dates.enums import KnowledgeDateListSort
from core.knowledge.exceptions import InvalidKnowledgeDataError
from core.knowledge.files.schemas import KnowledgeFile
from core.knowledge.items.schemas import KnowledgeItem, KnowledgeTag


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeDateValue:
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
class KnowledgeDateDetails:
    item_id: str
    date: KnowledgeDateValue


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeDatePersonLink:
    date_id: str
    person_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RelatedPerson:
    id: str
    display_name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeDateReference:
    id: str
    display_name: str
    date: KnowledgeDateValue


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeDate:
    item: KnowledgeItem
    details: KnowledgeDateDetails
    related_people: list[RelatedPerson]
    attachments: list[KnowledgeFile]


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeDateSummary:
    id: str
    display_name: str
    date: KnowledgeDateValue
    related_people: list[RelatedPerson]
    tags: list[KnowledgeTag]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeDatesPage:
    values: list[KnowledgeDateSummary]
    total_count: int
    total_pages: int

    @classmethod
    def from_values(
        cls,
        *,
        values: list[KnowledgeDateSummary],
        total_count: int,
        page_size: int,
    ) -> Self:
        return cls(
            values=values,
            total_count=total_count,
            total_pages=ceil(total_count / page_size) if total_count > 0 else 0,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeDateFilters:
    page: int
    page_size: int
    sort: KnowledgeDateListSort
    search_query: str | None
    tag_ids: tuple[str, ...]
    related_person_id: str | None
    author_username: str

    @property
    def limit(self) -> int:
        return self.page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeDateCreateParams:
    display_name: str
    date: KnowledgeDateValue
    author_username: str

    def __post_init__(self) -> None:
        if not self.display_name.strip():
            raise InvalidKnowledgeDataError


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeDateUpdateParams:
    display_name: str
    date: KnowledgeDateValue
    description: str
    tag_ids: list[str]
    person_ids: list[str]

    def __post_init__(self) -> None:
        if not self.display_name.strip() or len(self.person_ids) != len(set(self.person_ids)):
            raise InvalidKnowledgeDataError
