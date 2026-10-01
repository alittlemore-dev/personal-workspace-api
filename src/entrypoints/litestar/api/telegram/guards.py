import hmac
from typing import Any

from litestar.connection import ASGIConnection
from litestar.exceptions import HTTPException
from litestar.handlers.base import BaseRouteHandler

from core.telegram.enums import TelegramRuntimeStatus
from entrypoints.litestar.api.telegram.runtime import get_runtime_status
from infra.config.settings import settings


async def require_ready_bot(
    connection: ASGIConnection[Any, Any, Any, Any],
    _: BaseRouteHandler,
) -> None:
    if connection.scope.get("method") == "GET":
        return
    if await get_runtime_status(connection) != TelegramRuntimeStatus.READY:
        raise HTTPException(status_code=503, detail="Telegram bot is not ready")


def require_telegram_service(
    connection: ASGIConnection[Any, Any, Any, Any],
    _: BaseRouteHandler,
) -> None:
    expected = settings.telegram.service_secret.get_secret_value()
    supplied = connection.headers.get("X-Telegram-Service-Secret", "")
    if not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=403)
