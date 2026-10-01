import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from litestar import Litestar

from core.telegram.enums import TelegramRuntimeStatus
from infra.config.initializers import before_app_create
from infra.telegram.runtime import TelegramBotRuntime
from infra.valkey.telegram_delivery import TelegramDeliveryLease
from infra.valkey.telegram_runtime import TelegramRuntimeStatusStore


@asynccontextmanager
async def app_lifespan(app: Litestar) -> AsyncGenerator[None]:
    before_app_create()
    telegram_dispatcher = getattr(app.state, "telegram_dispatcher", None)
    runtime_task: asyncio.Task[None] | None = None
    status_store: TelegramRuntimeStatusStore | None = None
    try:
        if telegram_dispatcher is not None:
            status_store = app.state.telegram_runtime_status
            runtime = TelegramBotRuntime(
                bot=telegram_dispatcher.bot,
                state=app.state.telegram_runtime_state,
                status_store=status_store,
                delivery_lease=TelegramDeliveryLease.create(status_store),
                handle_update=telegram_dispatcher.feed_raw_update,
            )
            runtime_task = asyncio.create_task(runtime.run(), name="telegram-connection")
        yield
    finally:
        if runtime_task is not None:
            runtime_task.cancel()
            with suppress(asyncio.CancelledError):
                await runtime_task
        if status_store is not None:
            app.state.telegram_runtime_state.status = TelegramRuntimeStatus.FAILED
            await status_store.close()
        if telegram_dispatcher is not None:
            await telegram_dispatcher.close()
        await app.state.dishka_container.close()
