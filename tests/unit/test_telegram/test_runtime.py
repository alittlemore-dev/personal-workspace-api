import asyncio
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

import pytest
from taskiq import AsyncTaskiqDecoratedTask
from valkey.exceptions import ConnectionError as ValkeyConnectionError

from core.telegram.enums import TelegramRuntimeStatus
from entrypoints.taskiq.finance.tasks import send_finance_notifications
from entrypoints.taskiq.notifications.tasks import send_reminders
from infra.config.constants import constants
from infra.config.settings import settings
from infra.telegram.runtime import TelegramBotRuntime, TelegramRuntimeState
from infra.valkey.telegram_runtime import TelegramRuntimeStatusStore


@pytest.mark.asyncio
async def test_connection_failure_retries_recovers_and_detects_later_outage(
    capsys: pytest.CaptureFixture[str],
) -> None:
    bot = Mock()
    bot.set_webhook = AsyncMock(side_effect=[TimeoutError("PRIVATE_TOKEN"), True])
    bot.get_me = AsyncMock(side_effect=TimeoutError("PRIVATE_TOKEN"))
    store = Mock(spec=TelegramRuntimeStatusStore)
    store.publish = AsyncMock()
    state = TelegramRuntimeState(status=TelegramRuntimeStatus.CONNECTING)
    runtime = TelegramBotRuntime(bot=bot, state=state, status_store=store)
    observed: list[TelegramRuntimeStatus] = []

    async def next_attempt(_: float) -> None:
        observed.append(state.status)
        if len(observed) == 3:
            raise asyncio.CancelledError

    with (
        patch("infra.telegram.runtime.asyncio.sleep", side_effect=next_attempt),
        pytest.raises(asyncio.CancelledError),
    ):
        await runtime.run()
    assert observed == [
        TelegramRuntimeStatus.FAILED,
        TelegramRuntimeStatus.READY,
        TelegramRuntimeStatus.FAILED,
    ]
    assert bot.set_webhook.await_count == 2
    bot.get_me.assert_awaited_once()
    assert "PRIVATE_TOKEN" not in capsys.readouterr().out
    assert store.publish.await_args_list[-1].args == (TelegramRuntimeStatus.FAILED,)


@pytest.mark.asyncio
async def test_registration_timeout_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(constants.telegram, "connection_timeout_seconds", 0.01)
    bot = Mock()

    async def never_connects(**_: object) -> bool:
        await asyncio.Event().wait()
        return True

    bot.set_webhook = AsyncMock(side_effect=never_connects)
    store = Mock(spec=TelegramRuntimeStatusStore)
    store.publish = AsyncMock()
    state = TelegramRuntimeState(status=TelegramRuntimeStatus.CONNECTING)
    runtime = TelegramBotRuntime(bot=bot, state=state, status_store=store)
    with (
        patch("infra.telegram.runtime.asyncio.sleep", side_effect=asyncio.CancelledError),
        pytest.raises(asyncio.CancelledError),
    ):
        await asyncio.wait_for(runtime.run(), timeout=1)
    assert state.status == TelegramRuntimeStatus.FAILED


@pytest.mark.asyncio
async def test_readiness_store_fails_closed_for_expired_missing_or_failed_lease() -> None:
    valkey = Mock()
    valkey.get = AsyncMock(
        side_effect=[None, b"connecting", b"failed", b"ready", ValkeyConnectionError()],
    )
    store = TelegramRuntimeStatusStore(valkey=valkey, key="test-runtime", ttl_seconds=90)
    assert [await store.is_ready() for _ in range(5)] == [False, False, False, True, False]


@pytest.mark.asyncio
async def test_status_lease_has_expiry_and_deployment_slots_are_isolated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valkey = Mock()
    valkey.set = AsyncMock()
    store = TelegramRuntimeStatusStore(valkey=valkey, key="test-runtime", ttl_seconds=90)
    await store.publish(TelegramRuntimeStatus.READY)
    valkey.set.assert_awaited_once_with("test-runtime", "ready", ex=90)
    with patch("infra.valkey.telegram_runtime.Valkey.from_url", return_value=valkey):
        monkeypatch.setattr(settings.auth, "verify_url", "http://auth-blue/api/auth/verify")
        blue = TelegramRuntimeStatusStore.create()
        monkeypatch.setattr(settings.auth, "verify_url", "http://auth-green/api/auth/verify")
        green = TelegramRuntimeStatusStore.create()
    assert blue.key != green.key


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
