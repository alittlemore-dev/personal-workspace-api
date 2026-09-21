from unittest.mock import Mock

from dishka import Provider, Scope, provide

from core.cache_tools.schemas import CacheToolsPolicy
from core.cache_tools.use_cases import CacheToolsUseCase


class MockCacheToolsProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_cache_tools_policy(self) -> CacheToolsPolicy:
        return CacheToolsPolicy(
            enabled=True,
            configured_ttl_seconds=86_400,
            scheduled_warm_interval_seconds=3_600,
            domains=(),
        )

    @provide(scope=Scope.APP)
    async def provide_cache_tools_use_case(self) -> CacheToolsUseCase:
        return Mock(spec=CacheToolsUseCase)
