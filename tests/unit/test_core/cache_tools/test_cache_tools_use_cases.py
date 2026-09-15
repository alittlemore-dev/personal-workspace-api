from datetime import UTC, datetime
from unittest.mock import Mock, call

import pytest

from core.cache_tools.clients import CacheWarmExecutor
from core.cache_tools.enums import CacheDomainEnum, CacheWarmOperationStatusEnum
from core.cache_tools.event_dispatchers import CacheWarmTaskDispatcher
from core.cache_tools.exceptions import CacheWarmOperationNotFoundError
from core.cache_tools.schemas import (
    CacheDomainStatus,
    CacheToolsPolicy,
    CacheWarmOperation,
    CacheWarmSummary,
)
from core.cache_tools.storages import (
    CacheWarmOperationStorage,
    ResponseCacheInvalidationStorage,
    ResponseCacheStatusStorage,
)
from core.cache_tools.use_cases import CacheToolsUseCase, ManualCacheWarmUseCase
from core.generators import HexUuidIdGenerator

CURRENT_DATETIME = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
DOMAINS = (CacheDomainEnum.I18N,)


class TestCacheToolsUseCase:
    def setup_method(self) -> None:
        self.status_storage = Mock(spec=ResponseCacheStatusStorage)
        self.invalidation_storage = Mock(spec=ResponseCacheInvalidationStorage)
        self.operation_storage = Mock(spec=CacheWarmOperationStorage)
        self.dispatcher = Mock(spec=CacheWarmTaskDispatcher)
        self.id_generator = Mock(spec=HexUuidIdGenerator)
        self.id_generator.get_next.return_value = "operation-id"
        self.policy = CacheToolsPolicy(
            enabled=True,
            configured_ttl_seconds=86_400,
            scheduled_warm_interval_seconds=3_600,
            domains=DOMAINS,
        )
        self.use_case = CacheToolsUseCase(
            response_cache_status_storage=self.status_storage,
            response_cache_invalidation_storage=self.invalidation_storage,
            operation_storage=self.operation_storage,
            task_dispatcher=self.dispatcher,
            id_generator=self.id_generator,
        )

    async def test_get_status_reads_every_current_domain_and_latest_operation(self) -> None:
        domain_status = CacheDomainStatus(
            domain=CacheDomainEnum.I18N,
            key_count=3,
            minimum_remaining_ttl_seconds=120,
            non_expiring_key_count=1,
        )
        latest = CacheWarmOperation(
            operation_id="previous-operation",
            status=CacheWarmOperationStatusEnum.SUCCEEDED,
            queued_at=CURRENT_DATETIME,
            summary=CacheWarmSummary(attempted=3, written=3, skipped=0),
        )
        self.status_storage.get_domain_status.return_value = domain_status
        self.operation_storage.get_latest.return_value = latest

        result = await self.use_case.get_status(policy=self.policy)

        assert result.domains == (domain_status,)
        assert result.last_manual_warm_operation == latest
        assert self.status_storage.get_domain_status.await_args_list == [
            call(domain=CacheDomainEnum.I18N),
        ]

    async def test_disabled_status_does_not_read_response_cache(self) -> None:
        self.operation_storage.get_latest.return_value = None

        result = await self.use_case.get_status(
            policy=CacheToolsPolicy(
                enabled=False,
                configured_ttl_seconds=86_400,
                scheduled_warm_interval_seconds=3_600,
                domains=DOMAINS,
            ),
        )

        assert result.domains[0].key_count == 0
        self.status_storage.get_domain_status.assert_not_awaited()

    async def test_clear_invalidates_only_current_domains_and_refreshes_status(self) -> None:
        self.operation_storage.get_latest.return_value = None
        self.status_storage.get_domain_status.return_value = CacheDomainStatus(
            domain=CacheDomainEnum.I18N,
            key_count=0,
            minimum_remaining_ttl_seconds=None,
            non_expiring_key_count=0,
        )

        result = await self.use_case.clear(policy=self.policy)

        self.invalidation_storage.clear_domains.assert_awaited_once_with(domains=DOMAINS)
        assert result.domains[0].key_count == 0
        self.dispatcher.enqueue.assert_not_awaited()

    async def test_enqueue_manual_warm_persists_before_dispatch(self) -> None:
        calls: list[str] = []

        async def create_operation(operation: CacheWarmOperation) -> None:
            assert operation.status is CacheWarmOperationStatusEnum.QUEUED
            calls.append("create")

        async def enqueue(operation_id: str) -> None:
            assert operation_id == "operation-id"
            calls.append("enqueue")

        self.operation_storage.create.side_effect = create_operation
        self.dispatcher.enqueue.side_effect = enqueue

        result = await self.use_case.enqueue_manual_warm(current_datetime=CURRENT_DATETIME)

        assert result.operation_id == "operation-id"
        assert calls == ["create", "enqueue"]

    async def test_enqueue_failure_marks_operation_failed(self) -> None:
        self.dispatcher.enqueue.side_effect = RuntimeError("broker unavailable")

        with pytest.raises(RuntimeError, match="broker unavailable"):
            await self.use_case.enqueue_manual_warm(current_datetime=CURRENT_DATETIME)

        failed = self.operation_storage.update.await_args.kwargs["operation"]
        assert failed.status is CacheWarmOperationStatusEnum.FAILED

    async def test_unknown_manual_operation_is_rejected(self) -> None:
        self.operation_storage.get.return_value = None

        with pytest.raises(CacheWarmOperationNotFoundError):
            await self.use_case.get_manual_warm_operation(operation_id="missing")


class TestManualCacheWarmUseCase:
    def setup_method(self) -> None:
        self.operation_storage = Mock(spec=CacheWarmOperationStorage)
        self.executor = Mock(spec=CacheWarmExecutor)
        self.use_case = ManualCacheWarmUseCase(
            operation_storage=self.operation_storage,
            executor=self.executor,
        )
        self.operation_storage.get.return_value = CacheWarmOperation(
            operation_id="operation-id",
            status=CacheWarmOperationStatusEnum.QUEUED,
            queued_at=CURRENT_DATETIME,
            summary=None,
        )

    async def test_run_records_running_then_successful_lifecycle(self) -> None:
        summary = CacheWarmSummary(attempted=3, written=3, skipped=0)
        self.executor.warm_all.return_value = summary

        result = await self.use_case.run(operation_id="operation-id")

        assert result.summary == summary
        assert [
            update.kwargs["operation"].status
            for update in self.operation_storage.update.await_args_list
        ] == [
            CacheWarmOperationStatusEnum.RUNNING,
            CacheWarmOperationStatusEnum.SUCCEEDED,
        ]

    async def test_run_records_failed_lifecycle_and_reraises(self) -> None:
        self.executor.warm_all.side_effect = RuntimeError("warm failed")

        with pytest.raises(RuntimeError, match="warm failed"):
            await self.use_case.run(operation_id="operation-id")

        assert (
            self.operation_storage.update.await_args.kwargs["operation"].status
            is CacheWarmOperationStatusEnum.FAILED
        )
