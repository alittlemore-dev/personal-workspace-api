from entrypoints.litestar.api.routers import api_router


def test_protected_domain_routes_are_available_at_canonical_api_roots() -> None:
    route_paths = {route.path for route in api_router.routes}
    protected_paths = {
        "/api/tools/cache",
        "/api/calendar",
        "/api/files",
        "/api/resumes",
        "/api/knowledge/people",
        "/api/knowledge/dates",
        "/api/wiki-links/targets",
    }

    assert protected_paths <= route_paths


def test_public_api_keeps_healthcheck_and_i18n_routes() -> None:
    route_paths = {route.path for route in api_router.routes}

    assert {
        "/api/healthcheck",
        "/api/healthcheck/ready",
        "/api/i18n/languages",
        "/api/i18n/bundles/{language:str}",
    } <= route_paths
