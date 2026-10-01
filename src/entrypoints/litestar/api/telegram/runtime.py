from typing import Any

from litestar.connection import ASGIConnection

from core.telegram.enums import TelegramRuntimeStatus
from infra.config.settings import settings
from infra.valkey.telegram_runtime import TelegramRuntimeStatusStore


async def get_runtime_status(
    connection: ASGIConnection[Any, Any, Any, Any],
) -> TelegramRuntimeStatus:
    if not settings.telegram.available:
        return TelegramRuntimeStatus.DISABLED
    local_status: TelegramRuntimeStatus = connection.app.state.telegram_runtime_state.status
    if local_status != TelegramRuntimeStatus.READY:
        return local_status
    store: TelegramRuntimeStatusStore | None = getattr(
        connection.app.state,
        "telegram_runtime_status",
        None,
    )
    if store is None or not await store.is_ready():
        return TelegramRuntimeStatus.FAILED
    return TelegramRuntimeStatus.READY
