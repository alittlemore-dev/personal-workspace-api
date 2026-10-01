import asyncio
import json
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter, TelegramUnauthorizedError
from aiogram.methods import GetMe
from aiogram.types import User
from aiohttp_socks import ProxyConnectionError, ProxyError, ProxyTimeoutError
from taskiq import AsyncTaskiqDecoratedTask
from valkey.exceptions import ConnectionError as ValkeyConnectionError

from core.telegram.enums import TelegramRuntimeStatus
from entrypoints.taskiq.finance.tasks import send_finance_notifications
from entrypoints.taskiq.notifications.tasks import send_reminders
from infra.config.constants import constants
from infra.config.settings import SecretStrExtended, settings
from infra.telegram.bot import create_telegram_bot
from infra.telegram.runtime import TelegramBotRuntime, TelegramRuntimeState
from infra.valkey.telegram_delivery import TelegramDeliveryLease
from infra.valkey.telegram_runtime import TelegramRuntimeStatusStore


@pytest.fixture
def runtime() -> TelegramBotRuntime:
    config = settings.telegram.model_copy(
        update={
            "proxy_urls": [
                SecretStrExtended("http://primary.test:8080"),
                SecretStrExtended("http://backup.test:8080"),
            ],
        },
    )
    store = Mock(spec=TelegramRuntimeStatusStore)
    store.get_ready_route = AsyncMock(return_value=None)
    store.mark_failed = AsyncMock(return_value=True)
    store.publish = AsyncMock()
    store.publish_ready = AsyncMock()
    bot = create_telegram_bot(telegram_settings=config, runtime_status=store)
    lease = Mock(spec=TelegramDeliveryLease)
    lease.ensure_owned = AsyncMock()
    return TelegramBotRuntime(
        bot=bot,
        state=TelegramRuntimeState(status=TelegramRuntimeStatus.CONNECTING),
        status_store=store,
        delivery_lease=lease,
        handle_update=AsyncMock(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        TelegramNetworkError(method=GetMe(), message="failed"),
        ProxyConnectionError("failed"),
        ProxyTimeoutError("failed"),
        ProxyError("failed"),
    ],
)
async def test_primary_failure_uses_backup_and_recovered_primary_does_not_displace_it(
    runtime: TelegramBotRuntime,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    clock = [0.0]
    monkeypatch.setattr("infra.telegram.bot.monotonic", lambda: clock[0])
    user = User(id=123456, is_bot=True, first_name="Test")
    primary = AsyncMock(side_effect=[error, user])
    backup = AsyncMock(return_value=user)
    monkeypatch.setattr(runtime.transport.routes[0], "make_request", primary)
    monkeypatch.setattr(runtime.transport.routes[1], "make_request", backup)
    webhook = AsyncMock(return_value=True)
    monkeypatch.setattr(runtime.transport, "set_webhook", webhook)
    active = await runtime.connect(None, None)
    assert active == 1
    webhook.assert_awaited_once()
    assert webhook.await_args is not None
    assert webhook.await_args.args[1] == 1
    clock[0] = 31
    assert await runtime.connect(active, active) == 1
    assert await runtime.check_backup(active, 0) == 1
    assert primary.await_count == 2
    assert backup.await_count == 2
    assert webhook.await_count == 1


@pytest.mark.asyncio
async def test_total_outage_recovers_and_publishes_ready_only_after_webhook(
    runtime: TelegramBotRuntime,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clock = [0.0]
    monkeypatch.setattr("infra.telegram.bot.monotonic", lambda: clock[0])
    user = User(id=123456, is_bot=True, first_name="Test")
    failure = TelegramNetworkError(method=GetMe(), message="PRIVATE_TOKEN")
    primary = AsyncMock(side_effect=[failure, failure, user])
    backup = AsyncMock(side_effect=[user, failure, failure])
    monkeypatch.setattr(runtime.transport.routes[0], "make_request", primary)
    monkeypatch.setattr(runtime.transport.routes[1], "make_request", backup)
    store = cast("Mock", runtime.status_store)
    registered: list[int] = []

    async def register(_bot: Bot, index: int, _method: object) -> bool:
        registered.append(index)
        return True

    async def publish(index: int) -> None:
        assert registered[-1] == index

    monkeypatch.setattr(runtime.transport, "set_webhook", register)
    store.publish_ready.side_effect = publish
    observed: list[TelegramRuntimeStatus] = []

    async def next_attempt(_runtime: TelegramBotRuntime, _: float) -> None:
        observed.append(runtime.state.status)
        clock[0] += 31
        if len(observed) == 3:
            raise asyncio.CancelledError

    with (
        patch.object(TelegramBotRuntime, "wait", next_attempt),
        pytest.raises(asyncio.CancelledError),
    ):
        await runtime.monitor()
    assert observed == [
        TelegramRuntimeStatus.READY,
        TelegramRuntimeStatus.FAILED,
        TelegramRuntimeStatus.READY,
    ]
    assert [call.args[0] for call in store.publish_ready.await_args_list] == [1, 0]
    store.publish.assert_awaited_once_with(TelegramRuntimeStatus.FAILED)
    assert "PRIVATE_TOKEN" not in capsys.readouterr().out


@pytest.mark.asyncio
@pytest.mark.parametrize("error", ["token", "rate_limit"])
async def test_non_network_probe_failure_does_not_switch_proxy(
    runtime: TelegramBotRuntime,
    monkeypatch: pytest.MonkeyPatch,
    error: str,
) -> None:
    failures = {
        "token": TelegramUnauthorizedError(method=GetMe(), message="token"),
        "rate_limit": TelegramRetryAfter(method=GetMe(), message="rate limit", retry_after=30),
    }
    primary = AsyncMock(side_effect=failures[error])
    backup = AsyncMock()
    monkeypatch.setattr(runtime.transport.routes[0], "make_request", primary)
    monkeypatch.setattr(runtime.transport.routes[1], "make_request", backup)
    with pytest.raises(type(failures[error])):
        await runtime.connect(None, None)
    backup.assert_not_awaited()
    assert runtime.transport.candidate_available(0)


@pytest.mark.asyncio
async def test_cooldown_skips_failed_candidate_until_it_expires(
    runtime: TelegramBotRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    monkeypatch.setattr("infra.telegram.bot.monotonic", lambda: clock[0])
    primary = AsyncMock(side_effect=TimeoutError())
    backup = AsyncMock(side_effect=TimeoutError())
    monkeypatch.setattr(runtime.transport.routes[0], "make_request", primary)
    monkeypatch.setattr(runtime.transport.routes[1], "make_request", backup)
    for _ in range(2):
        with pytest.raises(TelegramNetworkError):
            await runtime.connect(None, None)
    primary.assert_awaited_once()
    backup.assert_awaited_once()
    clock[0] = 31
    with pytest.raises(TelegramNetworkError):
        await runtime.connect(None, None)
    assert primary.await_count == 2
    assert backup.await_count == 2


@pytest.mark.asyncio
async def test_registration_timeout_is_bounded(
    runtime: TelegramBotRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(constants.telegram, "connection_timeout_seconds", 0.01)
    monkeypatch.setattr(
        runtime.transport,
        "probe",
        AsyncMock(return_value=User(id=123456, is_bot=True, first_name="Test")),
    )

    async def never_connects(*_: object) -> bool:
        await asyncio.Event().wait()
        return True

    monkeypatch.setattr(runtime.transport, "set_webhook", never_connects)
    with (
        patch.object(TelegramBotRuntime, "wait", side_effect=asyncio.CancelledError),
        pytest.raises(asyncio.CancelledError),
    ):
        await asyncio.wait_for(runtime.monitor(), timeout=1)
    assert runtime.state.status == TelegramRuntimeStatus.FAILED


@pytest.mark.asyncio
async def test_readiness_store_fails_closed_for_missing_stale_invalid_and_store_failure() -> None:
    ready = {"status": "ready", "pool_id": "pool", "route_count": 2, "index": 1}
    values: list[object] = [
        None,
        b"ready",
        b"[]",
        b"{}",
        b"bad json",
        json.dumps({**ready, "status": "failed"}).encode(),
        json.dumps({**ready, "pool_id": "old pool"}).encode(),
        json.dumps({**ready, "route_count": 1}).encode(),
        json.dumps({**ready, "index": 2}).encode(),
        json.dumps({**ready, "index": True}).encode(),
        json.dumps(ready).encode(),
        ValkeyConnectionError(),
    ]
    valkey = Mock()
    valkey.get = AsyncMock(side_effect=values)
    store = TelegramRuntimeStatusStore(
        valkey=valkey,
        key="test-runtime",
        ttl_seconds=90,
        pool_id="pool",
        route_count=2,
    )
    assert [await store.get_ready_route() for _ in values] == [None] * 10 + [1, None]


@pytest.mark.asyncio
async def test_status_lease_is_atomic_expires_and_deployment_slots_are_isolated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valkey = Mock()
    valkey.set = AsyncMock()
    store = TelegramRuntimeStatusStore(
        valkey=valkey,
        key="test-runtime",
        ttl_seconds=90,
        pool_id="pool",
        route_count=2,
    )
    await store.publish_ready(1)
    call = valkey.set.await_args
    assert call.args[0] == "test-runtime"
    assert json.loads(call.args[1]) == {
        "status": "ready",
        "pool_id": "pool",
        "route_count": 2,
        "index": 1,
    }
    assert call.kwargs == {"ex": 90}
    with pytest.raises(ValueError, match="explicit route"):
        await store.publish(TelegramRuntimeStatus.READY)
    with pytest.raises(ValueError, match="outside"):
        await store.publish_ready(2)
    with patch("infra.valkey.telegram_runtime.Valkey.from_url", return_value=valkey):
        monkeypatch.setattr(settings.auth, "verify_url", "http://auth-blue/api/auth/verify")
        blue = TelegramRuntimeStatusStore.create()
        blue_delivery = TelegramDeliveryLease.create(blue)
        monkeypatch.setattr(settings.auth, "verify_url", "http://auth-green/api/auth/verify")
        monkeypatch.setattr(settings.telegram, "delivery_mode", "polling")
        monkeypatch.setattr(
            settings.telegram,
            "proxy_urls",
            [SecretStrExtended("http://new.test:8080")],
        )
        green = TelegramRuntimeStatusStore.create()
        green_delivery = TelegramDeliveryLease.create(green)
    assert blue.key != green.key
    assert blue.pool_id != green.pool_id
    assert blue_delivery.key == green_delivery.key


@pytest.mark.asyncio
@pytest.mark.parametrize("task", [send_reminders, send_finance_notifications])
async def test_notifications_are_not_claimed_until_bot_is_ready(
    task: AsyncTaskiqDecoratedTask[..., int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings.telegram, "available", True)
    use_case = Mock()
    use_case.run = AsyncMock(return_value=2)
    store = Mock(spec=TelegramRuntimeStatusStore)
    store.is_ready = AsyncMock(return_value=False)
    operation = cast("Any", task.original_func).__dishka_orig_func__
    now = datetime(2026, 10, 1, tzinfo=UTC)
    assert await operation(use_case=use_case, current_datetime=now, runtime_status=store) == 0
    use_case.run.assert_not_awaited()
    store.is_ready.return_value = True
    assert await operation(use_case=use_case, current_datetime=now, runtime_status=store) == 2
    use_case.run.assert_awaited_once_with(now=now)


@pytest.mark.asyncio
async def test_backup_timeout_enters_cooldown_without_interrupting_working_route(
    runtime: TelegramBotRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(constants.telegram, "connection_timeout_seconds", 0.01)
    runtime.state.status = TelegramRuntimeStatus.READY
    store = cast("Mock", runtime.status_store)
    store.mark_failed.return_value = False

    async def never_connects(*_: object, **__: object) -> User:
        await asyncio.Event().wait()
        return User(id=123456, is_bot=True, first_name="Test")

    backup = AsyncMock(side_effect=never_connects)
    monkeypatch.setattr(runtime.transport.routes[1], "make_request", backup)
    await runtime.check_backup(0, 1)
    await runtime.check_backup(0, 1)
    backup.assert_awaited_once()
    assert not runtime.transport.candidate_available(1)
    assert runtime.transport.candidate_available(0)
    assert runtime.state.status == TelegramRuntimeStatus.READY
    assert not runtime.transport.wake.is_set()
    store.publish.assert_not_awaited()
