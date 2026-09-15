from litestar import Router

from entrypoints.litestar.api.auth.endpoints import api_router as auth_router
from entrypoints.litestar.api.calendar.endpoints import api_router as calendar_router
from entrypoints.litestar.api.files.endpoints import api_router as files_router
from entrypoints.litestar.api.healthcheck.endpoints import api_router as healthcheck_router
from entrypoints.litestar.api.i18n.endpoints import api_router as i18n_router
from entrypoints.litestar.api.knowledge.router import api_router as knowledge_router
from entrypoints.litestar.api.resumes.endpoints import api_router as resumes_router
from entrypoints.litestar.api.tools.endpoints import api_router as tools_router
from entrypoints.litestar.api.wiki_links.endpoints import api_router as wiki_links_router
from entrypoints.litestar.guards import require_authenticated_user

protected_api_router = Router(
    "",
    route_handlers=[
        tools_router,
        calendar_router,
        files_router,
        resumes_router,
        knowledge_router,
        wiki_links_router,
    ],
    tags=["protected api"],
    include_in_schema=False,
    guards=[require_authenticated_user],
)

api_router = Router(
    "/api",
    route_handlers=[
        auth_router,
        healthcheck_router,
        i18n_router,
        protected_api_router,
    ],
    tags=["api"],
)
