from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from litestar import Litestar

from infra.config.initializers import before_app_create
from infra.config.settings import settings


@asynccontextmanager
async def app_lifespan(app: Litestar) -> AsyncGenerator[None]:
    before_app_create()
    telegram_dispatcher = getattr(app.state, "telegram_dispatcher", None)
    try:
        if telegram_dispatcher is not None:
            await telegram_dispatcher.bot.set_webhook(
                url=settings.app.get_url("api/personal-workspace/telegram/webhook"),
                secret_token=settings.telegram.webhook_secret.get_secret_value(),
                allowed_updates=["message"],
            )
        yield
    finally:
        if telegram_dispatcher is not None:
            await telegram_dispatcher.close()
        await app.state.dishka_container.close()
