from unittest.mock import AsyncMock, Mock, patch

import pytest

from entrypoints.litestar.lifespan.main import app_lifespan
from infra.config.settings import settings


@pytest.mark.asyncio
async def test_lifespan_registers_secret_webhook_and_closes_bot() -> None:
    dispatcher = Mock()
    dispatcher.bot.set_webhook = AsyncMock()
    dispatcher.close = AsyncMock()
    app = Mock()
    app.state.telegram_dispatcher = dispatcher
    app.state.dishka_container.close = AsyncMock()

    with patch("entrypoints.litestar.lifespan.main.before_app_create"):
        async with app_lifespan(app):
            pass

    dispatcher.bot.set_webhook.assert_awaited_once_with(
        url=settings.app.get_url("api/personal-workspace/telegram/webhook"),
        secret_token=settings.telegram.webhook_secret.get_secret_value(),
        allowed_updates=["message"],
    )
    dispatcher.close.assert_awaited_once()
    app.state.dishka_container.close.assert_awaited_once()
