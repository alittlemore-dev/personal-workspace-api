from litestar import Request

from core.knowledge.dates.schemas import KnowledgeDateFilters
from entrypoints.litestar.api.parameters import (
    KnowledgeDateListSortQuery,
    KnowledgeTagIdsQuery,
    PageQuery,
    PageSizeQuery,
    RelatedPersonIdQuery,
    SearchQueryFilter,
)


def provide_knowledge_date_filters(  # noqa: PLR0913
    request: Request,
    page: PageQuery,
    page_size: PageSizeQuery,
    sort: KnowledgeDateListSortQuery,
    search_query: SearchQueryFilter = None,
    tag_ids: KnowledgeTagIdsQuery = None,
    related_person_id: RelatedPersonIdQuery = None,
) -> KnowledgeDateFilters:
    normalized_search_query = (
        search_query.strip() if search_query is not None and search_query.strip() else None
    )
    return KnowledgeDateFilters(
        page=page,
        page_size=page_size,
        sort=sort,
        search_query=normalized_search_query,
        tag_ids=tuple(dict.fromkeys(tag_ids or [])),
        related_person_id=related_person_id,
        author_username=request.user.username,
    )
