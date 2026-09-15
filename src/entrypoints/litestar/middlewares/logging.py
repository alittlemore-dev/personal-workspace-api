import uuid

import structlog.contextvars
from litestar.connection import Request
from litestar.middleware import ASGIMiddleware
from litestar.middleware.logging import LoggingMiddleware
from litestar.types import ASGIApp, Receive, Scope, Send

from infra.config.constants import constants
from infra.config.loggers import logger


class RequestIdLoggingMiddleware(ASGIMiddleware):
    async def handle(self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp) -> None:
        structlog.contextvars.unbind_contextvars("request_id")
        structlog.contextvars.bind_contextvars(request_id=uuid.uuid4().__str__())
        await next_app(scope, receive, send)


class LogExceptionMiddleware(ASGIMiddleware):
    async def handle(self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp) -> None:
        try:
            await next_app(scope, receive, send)
        except Exception as exc:
            logger.exception(str(exc))
            raise


class PrivacySafeLoggingMiddleware(LoggingMiddleware):
    async def extract_request_data(self, request: Request) -> dict[str, object]:
        data = await super().extract_request_data(request=request)
        if request.url.path.startswith(
            constants.request_logging.private_knowledge_path_prefix,
        ):
            data["path"] = constants.request_logging.private_knowledge_safe_path
            data["path_params"] = {}
        return data
