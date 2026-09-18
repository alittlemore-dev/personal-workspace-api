from backend_sdk.auth import AuthenticationClient
from backend_sdk.auth.http import AuthApiClientConfig
from backend_sdk.integrations.litestar import AuthPlugin
from litestar import Litestar

from entrypoints.litestar.initializers.main import create_litestar_app
from entrypoints.litestar.lifespan.main import app_lifespan
from infra.config.settings import settings
from infra.ioc.container import container


def create_app(auth_client: AuthenticationClient | None = None) -> Litestar:
    auth_plugin = (
        AuthPlugin(auth_client=auth_client)
        if auth_client is not None
        else AuthPlugin(
            config=AuthApiClientConfig(
                verify_url=settings.auth.verify_url,
                timeout_seconds=settings.auth.timeout_seconds,
                cache_ttl_seconds=settings.auth.cache_ttl_seconds,
                max_cache_entries=settings.auth.max_cache_entries,
            ),
        )
    )
    return create_litestar_app(
        lifespan=[app_lifespan],
        container=container,
        extra_plugins=[auth_plugin],
        extra_middlewares=[],
    )
