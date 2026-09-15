# ruff: noqa: UP040
# Litestar 2.23 does not unwrap PEP 695 aliases in handler signatures.
from datetime import date
from typing import Annotated, TypeAlias

from litestar.enums import RequestEncodingType
from litestar.openapi.spec import Example
from litestar.params import BodyKwarg, PathParameter, QueryParameter

from core.calendar.enums import CalendarWindow
from core.files.enums import FilePurpose
from core.i18n.enums import LanguageEnum
from core.knowledge.dates.enums import KnowledgeDateListSort
from core.knowledge.people.enums import PersonListSort


def build_examples(*values: object) -> list[Example]:
    return [Example(value=value) for value in values]


def api_query_parameter(  # noqa: PLR0913
    *,
    name: str,
    title: str,
    description: str,
    examples: tuple[object, ...],
    ge: float | None,
    le: float | None,
    min_items: int | None,
    max_items: int | None,
) -> QueryParameter:
    return QueryParameter(
        name=name,
        title=title,
        description=description,
        examples=build_examples(*examples),
        ge=ge,
        le=le,
        min_items=min_items,
        max_items=max_items,
        schema_extra={"examples": list(examples)},
    )


def api_path_parameter(
    *,
    name: str,
    title: str,
    description: str,
    examples: tuple[object, ...],
) -> PathParameter:
    return PathParameter(
        name=name,
        title=title,
        description=description,
        examples=build_examples(*examples),
        schema_extra={"examples": list(examples)},
    )


def api_json_body(
    *,
    title: str,
    description: str,
    examples: tuple[object, ...],
) -> BodyKwarg:
    return BodyKwarg(
        title=title,
        description=description,
        examples=build_examples(*examples),
        media_type=RequestEncodingType.JSON,
        schema_extra={"examples": list(examples)},
    )


def api_multipart_body(
    *,
    title: str,
    description: str,
    examples: tuple[object, ...],
) -> BodyKwarg:
    return BodyKwarg(
        title=title,
        description=description,
        examples=build_examples(*examples),
        media_type=RequestEncodingType.MULTI_PART,
        schema_extra={"examples": list(examples)},
    )


PageQuery: TypeAlias = Annotated[
    int,
    api_query_parameter(
        name="page",
        title="Page",
        description="One-based page number.",
        examples=(1,),
        ge=1,
        le=None,
        min_items=None,
        max_items=None,
    ),
]
PageSizeQuery: TypeAlias = Annotated[
    int,
    api_query_parameter(
        name="pageSize",
        title="Page size",
        description="Number of items to return per page.",
        examples=(20,),
        ge=1,
        le=100,
        min_items=None,
        max_items=None,
    ),
]
CalendarReferenceDateQuery: TypeAlias = Annotated[
    date,
    api_query_parameter(
        name="referenceDate",
        title="Calendar reference date",
        description="Browser-local date used to select the calendar window.",
        examples=("2026-07-31",),
        ge=None,
        le=None,
        min_items=None,
        max_items=None,
    ),
]
CalendarWindowQuery: TypeAlias = Annotated[
    CalendarWindow,
    api_query_parameter(
        name="window",
        title="Calendar window",
        description="Single reference month or the reference and following months.",
        examples=(CalendarWindow.CURRENT_AND_NEXT_MONTHS.value,),
        ge=None,
        le=None,
        min_items=None,
        max_items=None,
    ),
]
PersonListSortQuery: TypeAlias = Annotated[
    PersonListSort,
    api_query_parameter(
        name="sort",
        title="People sort",
        description="Stable ordering for the private people workspace.",
        examples=(PersonListSort.UPDATED_NEWEST.value,),
        ge=None,
        le=None,
        min_items=None,
        max_items=None,
    ),
]
KnowledgeDateListSortQuery: TypeAlias = Annotated[
    KnowledgeDateListSort,
    api_query_parameter(
        name="sort",
        title="Dates sort",
        description="Stable ordering for the private memorable dates workspace.",
        examples=(KnowledgeDateListSort.DATE_ASC.value,),
        ge=None,
        le=None,
        min_items=None,
        max_items=None,
    ),
]
RelatedPersonIdQuery: TypeAlias = Annotated[
    str | None,
    api_query_parameter(
        name="relatedPersonId",
        title="Related person identifier",
        description="Optional author-scoped person backlink filter.",
        examples=("00000000000000000000000000000001",),
        ge=None,
        le=None,
        min_items=None,
        max_items=None,
    ),
]
KnowledgeTagIdsQuery: TypeAlias = Annotated[
    list[str] | None,
    api_query_parameter(
        name="tagIds",
        title="Knowledge tag identifiers",
        description="Optional tag identifiers combined with AND semantics.",
        examples=(["00000000000000000000000000000001"],),
        ge=None,
        le=None,
        min_items=None,
        max_items=None,
    ),
]
LanguageQuery: TypeAlias = Annotated[
    LanguageEnum,
    api_query_parameter(
        name="language",
        title="Language",
        description="Language used for localized response fields.",
        examples=(LanguageEnum.RU.value, LanguageEnum.EN.value),
        ge=None,
        le=None,
        min_items=None,
        max_items=None,
    ),
]
SearchQueryFilter: TypeAlias = Annotated[
    str | None,
    api_query_parameter(
        name="searchQuery",
        title="Search query",
        description="Optional free-text filter. Blank values are ignored.",
        examples=("person",),
        ge=None,
        le=None,
        min_items=None,
        max_items=None,
    ),
]
PersonIdPath: TypeAlias = Annotated[
    str,
    api_path_parameter(
        name="person_id",
        title="Person ID",
        description="Private person identifier.",
        examples=("00000000000000000000000000000001",),
    ),
]
KnowledgeDateIdPath: TypeAlias = Annotated[
    str,
    api_path_parameter(
        name="date_id",
        title="Knowledge date ID",
        description="Private memorable date identifier.",
        examples=("00000000000000000000000000000001",),
    ),
]
KnowledgeItemIdPath: TypeAlias = Annotated[
    str,
    api_path_parameter(
        name="item_id",
        title="Knowledge item ID",
        description="Private knowledge item identifier.",
        examples=("00000000000000000000000000000001",),
    ),
]
KnowledgeFileIdPath: TypeAlias = Annotated[
    str,
    api_path_parameter(
        name="file_id",
        title="Knowledge file ID",
        description="Private author-scoped knowledge file identifier.",
        examples=("00000000000000000000000000000001",),
    ),
]
KnowledgeTagIdPath: TypeAlias = Annotated[
    str,
    api_path_parameter(
        name="tag_id",
        title="Knowledge tag ID",
        description="Author-scoped knowledge tag identifier.",
        examples=("00000000000000000000000000000001",),
    ),
]
PersonRelationshipTypeIdPath: TypeAlias = Annotated[
    str,
    api_path_parameter(
        name="relationship_type_id",
        title="Person relationship type ID",
        description="Author-scoped relationship type identifier.",
        examples=("00000000000000000000000000000001",),
    ),
]
FilePurposeQuery: TypeAlias = Annotated[
    FilePurpose,
    api_query_parameter(
        name="purpose",
        title="File purpose",
        description="Managed-file purpose namespace.",
        examples=(FilePurpose.ATTACHMENT.value,),
        ge=None,
        le=None,
        min_items=None,
        max_items=None,
    ),
]
FileIdPath: TypeAlias = Annotated[
    str,
    api_path_parameter(
        name="file_id",
        title="File identifier",
        description="Managed file identifier.",
        examples=("00000000000000000000000000000003",),
    ),
]
ResumeIdPath: TypeAlias = Annotated[
    str,
    api_path_parameter(
        name="resume_id",
        title="Resume identifier",
        description="Resume workspace identifier.",
        examples=("00000000000000000000000000000004",),
    ),
]
I18nLanguagePath: TypeAlias = Annotated[
    LanguageEnum,
    api_path_parameter(
        name="language",
        title="Language",
        description="Interface language code for the requested i18n bundle.",
        examples=(LanguageEnum.RU.value, LanguageEnum.EN.value),
    ),
]
