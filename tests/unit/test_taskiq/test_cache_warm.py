from unittest.mock import Mock

import pytest

from entrypoints.litestar.response_cache import ResponseCacheDomain
from entrypoints.taskiq.cache_warm.service import CacheWarmSummary, ResponseCacheWarmService
from entrypoints.taskiq.cache_warm.targets import ResponseCacheWarmTargetCollector
from entrypoints.taskiq.cache_warm.writer import ResponseCacheWarmWriter


@pytest.mark.parametrize("use_cache", [True, False])
async def test_workspace_has_no_product_cache_targets(use_cache: bool) -> None:
    writer = Mock(spec=ResponseCacheWarmWriter)
    collector = ResponseCacheWarmTargetCollector()
    service = ResponseCacheWarmService(
        target_collector=collector,
        writer=writer,
        use_cache=use_cache,
        supported_domains=(),
    )

    assert await collector.collect(domains=tuple(ResponseCacheDomain)) == []
    assert await service.warm_all() == CacheWarmSummary(attempted=0, written=0, skipped=0)
    assert await service.warm_domain(domain=ResponseCacheDomain.HEALTHCHECK) == CacheWarmSummary(
        attempted=0,
        written=0,
        skipped=1,
    )
    writer.write_target.assert_not_awaited()
