from backend_sdk import RoleEnum
from backend_sdk.integrations.litestar import RequireRole
from litestar import Router

from entrypoints.litestar.api.calendar.endpoints import api_router as calendar_router
from entrypoints.litestar.api.events.endpoints import api_router as events_router
from entrypoints.litestar.api.files.endpoints import api_router as files_router
from entrypoints.litestar.api.finance.endpoints import api_router as finance_router
from entrypoints.litestar.api.healthcheck.endpoints import api_router as healthcheck_router
from entrypoints.litestar.api.important_info.endpoints import api_router as important_info_router
from entrypoints.litestar.api.knowledge.router import api_router as knowledge_router
from entrypoints.litestar.api.resumes.endpoints import api_router as resumes_router
from entrypoints.litestar.api.telegram.endpoints import api_router as telegram_router
from entrypoints.litestar.api.tools.endpoints import api_router as tools_router
from entrypoints.litestar.api.vault.endpoints import api_router as vault_router
from entrypoints.litestar.api.wiki_links.endpoints import api_router as wiki_links_router

protected_api_router = Router(
    "",
    route_handlers=[
        tools_router,
        calendar_router,
        events_router,
        finance_router,
        important_info_router,
        files_router,
        resumes_router,
        knowledge_router,
        wiki_links_router,
        vault_router,
    ],
    tags=["protected api"],
    security=[{"bearerAuth": []}],
    guards=[RequireRole(RoleEnum.USER)],
)

api_router = Router(
    "/api",
    route_handlers=[
        healthcheck_router,
        telegram_router,
        protected_api_router,
    ],
    tags=["api"],
)
