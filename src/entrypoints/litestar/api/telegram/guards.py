import hmac
from typing import Any

from litestar.connection import ASGIConnection
from litestar.exceptions import HTTPException
from litestar.handlers.base import BaseRouteHandler

from core.telegram.enums import TelegramRuntimeStatus
from infra.config.settings import settings


def require_ready_bot(connection: ASGIConnection[Any, Any, Any, Any], _: BaseRouteHandler) -> None:
    if connection.scope.get("method") == "GET":
        return
    if (
        not settings.telegram.available
        or connection.app.state.telegram_runtime_state.status != TelegramRuntimeStatus.READY
    ):
        raise HTTPException(status_code=503, detail="Telegram bot is not ready")


def require_telegram_service(
    connection: ASGIConnection[Any, Any, Any, Any],
    _: BaseRouteHandler,
) -> None:
    expected = settings.telegram.service_secret.get_secret_value()
    supplied = connection.headers.get("X-Telegram-Service-Secret", "")
    if not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=403)
