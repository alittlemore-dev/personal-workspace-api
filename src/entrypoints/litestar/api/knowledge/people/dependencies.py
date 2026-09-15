from litestar import Request

from core.knowledge.people.schemas import PersonFilters
from entrypoints.litestar.api.parameters import (
    KnowledgeTagIdsQuery,
    PageQuery,
    PageSizeQuery,
    PersonListSortQuery,
    SearchQueryFilter,
)


def provide_person_filters(  # noqa: PLR0913
    request: Request,
    page: PageQuery,
    page_size: PageSizeQuery,
    sort: PersonListSortQuery,
    search_query: SearchQueryFilter = None,
    tag_ids: KnowledgeTagIdsQuery = None,
) -> PersonFilters:
    normalized_search_query = (
        search_query.strip() if search_query is not None and search_query.strip() else None
    )
    return PersonFilters(
        page=page,
        page_size=page_size,
        sort=sort,
        search_query=normalized_search_query,
        tag_ids=tuple(dict.fromkeys(tag_ids or [])),
        author_username=request.user.username,
    )
