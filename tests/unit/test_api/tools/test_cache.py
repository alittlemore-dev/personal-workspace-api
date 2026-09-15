from datetime import UTC, datetime

import pytest_asyncio
from httpx import codes

from core.cache_tools.enums import CacheDomainEnum, CacheWarmOperationStatusEnum
from core.cache_tools.exceptions import CacheWarmOperationNotFoundError
from core.cache_tools.schemas import (
    CacheDomainStatus,
    CacheToolsStatus,
    CacheWarmOperation,
    CacheWarmSummary,
)
from entrypoints.litestar.api.tools.endpoints import ToolsApiController
from tests.test_cases import ApiTestCase

QUEUED_AT = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def cache_status() -> CacheToolsStatus:
    return CacheToolsStatus(
        enabled=True,
        configured_ttl_seconds=86_400,
        scheduled_warm_interval_seconds=3_600,
        domains=(
            CacheDomainStatus(
                domain=CacheDomainEnum.I18N,
                key_count=3,
                minimum_remaining_ttl_seconds=120,
                non_expiring_key_count=1,
            ),
        ),
        last_manual_warm_operation=CacheWarmOperation(
            operation_id="previous-operation",
            status=CacheWarmOperationStatusEnum.SUCCEEDED,
            queued_at=QUEUED_AT,
            summary=CacheWarmSummary(attempted=3, written=3, skipped=0),
        ),
    )


class TestToolsCacheApi(ApiTestCase):
    @pytest_asyncio.fixture(autouse=True)
    async def setup(self) -> None:
        self.use_case = await self.container.get_cache_tools_use_case()
        self.policy = await self.container.get_cache_tools_policy()

    def test_get_cache_status_exposes_only_current_domain(self) -> None:
        self.use_case.get_status.return_value = cache_status()

        response = self.api.get_tools_cache()

        self.asserts.status(response=response, expected_status=codes.OK)
        assert response.json()["domains"] == [
            {
                "domain": "i18n",
                "keyCount": 3,
                "minimumRemainingTtlSeconds": 120,
                "nonExpiringKeyCount": 1,
            },
        ]
        self.use_case.get_status.assert_awaited_once_with(policy=self.policy)

    def test_clear_returns_refreshed_status_without_warming(self) -> None:
        self.use_case.clear.return_value = cache_status()

        response = self.api.post_tools_cache_clear()

        self.asserts.status(response=response, expected_status=codes.OK)
        self.use_case.clear.assert_awaited_once_with(policy=self.policy)
        self.use_case.enqueue_manual_warm.assert_not_awaited()

    def test_manual_warm_returns_pollable_operation(self) -> None:
        self.use_case.enqueue_manual_warm.return_value = CacheWarmOperation(
            operation_id="operation-id",
            status=CacheWarmOperationStatusEnum.QUEUED,
            queued_at=QUEUED_AT,
            summary=None,
        )

        response = self.api.post_tools_cache_warm()

        self.asserts.status(response=response, expected_status=codes.ACCEPTED)
        assert response.json()["operationId"] == "operation-id"
        assert response.json()["status"] == "queued"

    def test_unknown_manual_warm_operation_returns_not_found(self) -> None:
        self.use_case.get_manual_warm_operation.side_effect = CacheWarmOperationNotFoundError()

        response = self.api.get_tools_cache_warm_operation(operation_id="missing")

        self.asserts.status(response=response, expected_status=codes.NOT_FOUND)

    def test_handlers_are_never_response_cached(self) -> None:
        assert ToolsApiController.get_cache_status.cache is False
        assert ToolsApiController.clear_cache.cache is False
        assert ToolsApiController.warm_cache.cache is False
        assert ToolsApiController.get_cache_warm_operation.cache is False
