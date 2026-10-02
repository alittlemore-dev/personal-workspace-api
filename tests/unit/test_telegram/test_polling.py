import asyncio
from typing import cast
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import DeleteWebhook, GetUpdates
from aiogram.types import Update, User

from core.telegram.enums import TelegramRuntimeStatus
from infra.config.settings import settings
from infra.telegram.bot import TelegramFailoverSession
from infra.telegram.commands import TelegramCommandMenu
from infra.telegram.polling import TelegramPollingReceiver
from infra.telegram.runtime import TelegramBotRuntime, TelegramRuntimeState
from infra.valkey.telegram_delivery import TelegramDeliveryLease, TelegramDeliveryLeaseLostError
from infra.valkey.telegram_runtime import TelegramRuntimeStatusStore


@pytest.fixture
def polling_runtime(monkeypatch: pytest.MonkeyPatch) -> TelegramBotRuntime:
    monkeypatch.setattr(TelegramCommandMenu, "configure", AsyncMock())
    monkeypatch.setattr(settings.telegram, "delivery_mode", "polling")
    transport = Mock(spec=TelegramFailoverSession)
    transport.routes = (Mock(), Mock())
    transport.candidate_available.return_value = True
    transport.wake = asyncio.Event()
    transport.probe = AsyncMock(return_value=User(id=123456, is_bot=True, first_name="Test"))
    transport.request_candidate = AsyncMock(return_value=True)
    transport.request_route = AsyncMock()
    transport.mark_failed = AsyncMock()
    store = Mock(spec=TelegramRuntimeStatusStore)
    store.get_ready_route = AsyncMock(return_value=None)
    store.publish_ready = AsyncMock()
    store.publish = AsyncMock()
    lease = Mock(spec=TelegramDeliveryLease)
    lease.ensure_owned = AsyncMock()
    bot = Mock()
    bot.session = transport
    return TelegramBotRuntime(
        bot=bot,
        state=TelegramRuntimeState(status=TelegramRuntimeStatus.CONNECTING),
        status_store=store,
        delivery_lease=lease,
        handle_update=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_polling_removes_webhook_preserving_pending_updates_and_reuses_connection(
    polling_runtime: TelegramBotRuntime,
) -> None:
    runtime = polling_runtime
    assert await runtime.connect(None, None) == 0
    call = cast("AsyncMock", runtime.transport.request_candidate).await_args
    assert call is not None
    assert isinstance(call.kwargs["method"], DeleteWebhook)
    assert call.kwargs["method"].drop_pending_updates is False
    assert await runtime.connect(0, 0) == 0
    cast("AsyncMock", runtime.transport.request_candidate).assert_awaited_once()
    cast("Mock", runtime.transport.set_webhook).assert_not_called()


@pytest.mark.asyncio
async def test_polling_reports_ready_after_response_and_confirms_only_handled_updates(
    polling_runtime: TelegramBotRuntime,
) -> None:
    runtime = polling_runtime
    transport = cast("Mock", runtime.transport)
    calls: list[GetUpdates] = []

    async def receive(**kwargs: object) -> list[Update]:
        method = cast("GetUpdates", kwargs["method"])
        calls.append(method)
        assert method.timeout is not None
        assert cast("int", kwargs["request_timeout"]) > method.timeout
        if len(calls) == 1:
            assert runtime.state.status == TelegramRuntimeStatus.CONNECTING
            cast("Mock", runtime.status_store).publish_ready.assert_not_awaited()
            return [Update(update_id=41), Update(update_id=42)]
        assert [
            call.args[0] for call in cast("AsyncMock", runtime.handle_update).await_args_list
        ] == [
            {"update_id": 41},
            {"update_id": 42},
        ]
        assert runtime.state.status == TelegramRuntimeStatus.READY
        raise asyncio.CancelledError

    transport.request_route.side_effect = receive
    with pytest.raises(asyncio.CancelledError):
        await TelegramPollingReceiver(runtime=runtime).run()
    assert [method.offset for method in calls] == [None, 43]
    assert calls[0].timeout == 0
    assert calls[1].timeout is not None
    assert calls[1].timeout > 0
    assert calls[0].allowed_updates == ["message", "callback_query"]
    cast("AsyncMock", TelegramCommandMenu.configure).assert_awaited_once_with(0)


@pytest.mark.asyncio
async def test_polling_proxy_failure_keeps_offset_and_recovers_through_backup(
    polling_runtime: TelegramBotRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = polling_runtime
    transport = cast("Mock", runtime.transport)
    calls: list[tuple[int, int | None]] = []

    async def receive(**kwargs: object) -> list[Update]:
        method = cast("GetUpdates", kwargs["method"])
        calls.append((cast("int", kwargs["index"]), method.offset))
        if len(calls) == 1:
            return [Update(update_id=41)]
        if len(calls) == 2:
            transport.candidate_available.side_effect = lambda index: index == 1
            raise TelegramNetworkError(method=method, message="PRIVATE_PASSWORD")
        if len(calls) == 3:
            assert runtime.state.status == TelegramRuntimeStatus.FAILED
            return [Update(update_id=42)]
        raise asyncio.CancelledError

    transport.request_route.side_effect = receive
    monkeypatch.setattr(TelegramBotRuntime, "wait", AsyncMock())
    with pytest.raises(asyncio.CancelledError):
        await TelegramPollingReceiver(runtime=runtime).run()
    assert calls == [(0, None), (0, 42), (1, 42), (1, 43)]
    transport.mark_failed.assert_awaited_once_with(0, notify_monitor=False)
    cast("Mock", runtime.status_store).publish.assert_awaited_once_with(
        TelegramRuntimeStatus.FAILED,
    )
    assert runtime.state.status == TelegramRuntimeStatus.READY


@pytest.mark.asyncio
async def test_handler_failure_is_logged_without_replaying_completed_or_failed_commands(
    polling_runtime: TelegramBotRuntime,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = polling_runtime
    cast("Mock", runtime.transport).request_route.side_effect = [
        [Update(update_id=41), Update(update_id=42), Update(update_id=43)],
        asyncio.CancelledError,
    ]
    cast("AsyncMock", runtime.handle_update).side_effect = [
        None,
        RuntimeError("PRIVATE_TOKEN"),
        None,
    ]
    with pytest.raises(asyncio.CancelledError):
        await TelegramPollingReceiver(runtime=runtime).run()
    assert cast("AsyncMock", runtime.handle_update).await_count == 3
    calls = cast("Mock", runtime.transport).request_route.await_args_list
    assert [call.kwargs["method"].offset for call in calls] == [None, 44]
    log = capsys.readouterr().out
    assert "Telegram update handling failed" in log
    assert "PRIVATE_TOKEN" not in log


@pytest.mark.asyncio
async def test_uncertain_handler_send_is_attempted_once_and_unhandled_batch_waits_for_recovery(
    polling_runtime: TelegramBotRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = polling_runtime
    transport = cast("Mock", runtime.transport)
    transport.request_route.side_effect = [
        [Update(update_id=41), Update(update_id=42)],
        [Update(update_id=42)],
        asyncio.CancelledError,
    ]
    accepted_sends: list[int] = []

    async def handle(update: dict[str, object]) -> None:
        accepted_sends.append(cast("int", update["update_id"]))
        if update["update_id"] == 41:
            transport.candidate_available.side_effect = lambda index: index == 1
            raise TelegramNetworkError(
                method=GetUpdates(),
                message="response lost after accepted reply",
            )

    runtime.handle_update = handle
    monkeypatch.setattr(TelegramBotRuntime, "wait", AsyncMock())
    with pytest.raises(asyncio.CancelledError):
        await TelegramPollingReceiver(runtime=runtime).run()
    assert accepted_sends == [41, 42]
    calls = transport.request_route.await_args_list
    assert [call.kwargs["method"].offset for call in calls] == [None, 42, 43]
    assert [call.kwargs["index"] for call in calls] == [0, 1, 1]


@pytest.mark.asyncio
async def test_rate_limit_waits_full_retry_after_without_switching_proxy(
    polling_runtime: TelegramBotRuntime,
) -> None:
    runtime = polling_runtime
    transport = cast("Mock", runtime.transport)
    transport.request_route.side_effect = [
        TelegramRetryAfter(method=GetUpdates(), message="test rate limit", retry_after=11),
        [],
        asyncio.CancelledError,
    ]
    with (
        patch("infra.telegram.polling.asyncio.sleep", new_callable=AsyncMock) as sleep,
        pytest.raises(asyncio.CancelledError),
    ):
        await TelegramPollingReceiver(runtime=runtime).run()
    sleep.assert_awaited_once_with(11)
    transport.mark_failed.assert_not_awaited()
    assert {call.kwargs["index"] for call in transport.request_route.await_args_list} == {0}


@pytest.mark.asyncio
async def test_lost_delivery_lease_after_poll_does_not_dispatch_or_publish_ready(
    polling_runtime: TelegramBotRuntime,
) -> None:
    runtime = polling_runtime
    cast("Mock", runtime.transport).request_route.return_value = [Update(update_id=41)]
    cast("Mock", runtime.delivery_lease).ensure_owned.side_effect = [
        None,
        TelegramDeliveryLeaseLostError(),
    ]
    with pytest.raises(TelegramDeliveryLeaseLostError):
        await TelegramPollingReceiver(runtime=runtime).run()
    cast("AsyncMock", runtime.handle_update).assert_not_awaited()
    cast("Mock", runtime.status_store).publish_ready.assert_not_awaited()


@pytest.mark.asyncio
async def test_standby_neither_registers_webhook_nor_polls_nor_invalidates_readiness(
    polling_runtime: TelegramBotRuntime,
) -> None:
    runtime = polling_runtime
    lease = cast("Mock", runtime.delivery_lease)
    lease.acquire = AsyncMock(return_value=False)
    lease.release = AsyncMock()
    cast("Mock", runtime.status_store).is_ready = AsyncMock(return_value=True)
    with (
        patch.object(TelegramBotRuntime, "wait", side_effect=asyncio.CancelledError),
        pytest.raises(asyncio.CancelledError),
    ):
        await runtime.run()
    assert runtime.state.status == TelegramRuntimeStatus.READY
    cast("Mock", runtime.transport).probe.assert_not_awaited()
    cast("Mock", runtime.transport).request_route.assert_not_awaited()
    cast("Mock", runtime.status_store).publish.assert_not_awaited()
    lease.release.assert_not_awaited()


@pytest.mark.asyncio
async def test_lease_renewal_failure_cancels_blocked_poll_and_releases_owner(
    polling_runtime: TelegramBotRuntime,
) -> None:
    runtime = polling_runtime
    lease = cast("Mock", runtime.delivery_lease)
    lease.acquire = AsyncMock(return_value=True)
    lease.release = AsyncMock()
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def lost_lease() -> None:
        await entered.wait()
        raise TelegramDeliveryLeaseLostError

    async def blocked_poll(**_: object) -> list[Update]:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return []

    lease.keep_alive = AsyncMock(side_effect=lost_lease)
    cast("Mock", runtime.transport).request_route.side_effect = blocked_poll
    with (
        patch.object(TelegramBotRuntime, "wait", side_effect=asyncio.CancelledError),
        pytest.raises(asyncio.CancelledError),
    ):
        await asyncio.wait_for(runtime.run(), timeout=1)
    assert cancelled.is_set()
    assert runtime.state.status == TelegramRuntimeStatus.FAILED
    lease.release.assert_awaited_once()
