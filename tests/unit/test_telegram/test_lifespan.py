import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiogram.types import User

from core.telegram.enums import TelegramRuntimeStatus
from entrypoints.litestar.lifespan.main import app_lifespan
from infra.config.settings import settings
from infra.telegram.bot import TelegramFailoverSession
from infra.telegram.runtime import TelegramRuntimeState
from infra.valkey.telegram_runtime import TelegramRuntimeStatusStore


@pytest.mark.asyncio
async def test_lifespan_does_not_wait_for_webhook_and_cancels_connection_on_shutdown() -> None:
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def blocked_registration(*_: object) -> bool:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return True

    dispatcher = Mock()
    session = Mock(spec=TelegramFailoverSession)
    session.routes = (Mock(),)
    session.wake = asyncio.Event()
    session.candidate_available.return_value = True
    session.probe = AsyncMock(return_value=User(id=123456, is_bot=True, first_name="Test"))
    session.set_webhook = AsyncMock(side_effect=blocked_registration)
    dispatcher.bot.session = session
    dispatcher.close = AsyncMock()
    app = Mock()
    app.state.telegram_dispatcher = dispatcher
    app.state.telegram_runtime_state = TelegramRuntimeState(status=TelegramRuntimeStatus.CONNECTING)
    app.state.dishka_container.close = AsyncMock()
    store = Mock(spec=TelegramRuntimeStatusStore)
    store.publish = AsyncMock()
    store.get_ready_route = AsyncMock(return_value=None)
    app.state.telegram_runtime_status = store
    store.close = AsyncMock()

    with (
        patch("entrypoints.litestar.lifespan.main.before_app_create"),
    ):
        async with app_lifespan(app):
            await asyncio.wait_for(entered.wait(), timeout=1)
            assert app.state.telegram_runtime_state.status == TelegramRuntimeStatus.CONNECTING
            assert not cancelled.is_set()

    assert cancelled.is_set()
    session.set_webhook.assert_awaited_once()
    method = session.set_webhook.await_args.args[2]
    assert method.url == settings.app.get_url("api/personal-workspace/telegram/webhook")
    assert method.secret_token == settings.telegram.webhook_secret.get_secret_value()
    assert method.allowed_updates == ["message", "callback_query"]
    store.close.assert_awaited_once()
    dispatcher.close.assert_awaited_once()
    app.state.dishka_container.close.assert_awaited_once()
    assert app.state.telegram_runtime_state.status == TelegramRuntimeStatus.FAILED


@pytest.mark.asyncio
async def test_disabled_bot_starts_without_connection_task() -> None:
    app = Mock()
    app.state.telegram_dispatcher = None
    app.state.telegram_runtime_status = None
    app.state.dishka_container.close = AsyncMock()
    with (
        patch("entrypoints.litestar.lifespan.main.before_app_create"),
        patch.object(TelegramRuntimeStatusStore, "create") as create,
    ):
        async with app_lifespan(app):
            create.assert_not_called()
    app.state.dishka_container.close.assert_awaited_once()
