from litestar import Request

from core.resumes.schemas import ResumeFilters
from entrypoints.litestar.api.parameters import PageQuery, PageSizeQuery


def provide_resume_filters(
    request: Request,
    page: PageQuery,
    page_size: PageSizeQuery,
) -> ResumeFilters:
    return ResumeFilters(
        page=page,
        page_size=page_size,
        search_query=None,
        author_username=request.user.username,
    )
