import re
from collections.abc import Mapping
from hashlib import sha256
from typing import Any

from litestar.config.csrf import CSRFConfig
from litestar.connection import ASGIConnection
from litestar.datastructures import MutableScopeHeaders
from litestar.enums import ScopeType
from litestar.exceptions import SerializationException
from litestar.middleware.session.client_side import ClientSideSessionBackend, CookieBackendConfig
from litestar.security.session_auth import SessionAuth
from litestar.security.session_auth.middleware import SessionAuthMiddleware
from litestar.types import Message, Receive, Scope, Send

from core.auth.schemas import User
from infra.config.settings import settings

CSRF_EXCLUDED_PATHS = [r"^/api/auth/login$"]
PROTECTED_HTTP_PATH_PATTERN = re.compile(
    r"^/api/(?:(?:tools|calendar|files|resumes|knowledge|wiki-links)(?:/.*)?|auth/(?:session|logout)|docs(?:/.*)?)$"
)


class ProtectedPathSessionAuthMiddleware(SessionAuthMiddleware):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != ScopeType.HTTP or not PROTECTED_HTTP_PATH_PATTERN.match(scope["path"]):
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


class FailClosedCookieSessionBackend(ClientSideSessionBackend):
    async def load_from_connection(
        self,
        connection: ASGIConnection[Any, Any, Any, Any],
    ) -> dict[str, Any]:
        try:
            return await super().load_from_connection(connection)
        except KeyError, SerializationException, TypeError, ValueError:
            return {}


class FailClosedCookieBackendConfig(CookieBackendConfig):
    _backend_class = FailClosedCookieSessionBackend


def retrieve_authenticated_user(
    session: Mapping[str, object],
    _connection: ASGIConnection[Any, Any, Any, Any],
) -> User | None:
    if (
        not isinstance(session, dict)
        or set(session) != {"username"}
        or not isinstance(session["username"], str)
        or session["username"] != settings.owner.username
    ):
        return None
    return User(username=settings.owner.username)


def create_session_auth() -> SessionAuth[User, ClientSideSessionBackend]:
    return SessionAuth(
        session_backend_config=FailClosedCookieBackendConfig(
            secret=sha256(settings.app.secret_key.get_secret_value().encode()).digest(),
            key="personal_workspace_session",
            max_age=settings.auth.session_ttl_seconds,
            path="/",
            secure=settings.app.url_schema == "https",
            httponly=True,
            samesite="strict",
        ),
        retrieve_user_handler=retrieve_authenticated_user,
        authentication_middleware_class=ProtectedPathSessionAuthMiddleware,
        exclude=None,
    )


def create_csrf_config() -> CSRFConfig:
    return CSRFConfig(
        secret=settings.app.secret_key.get_secret_value(),
        cookie_name="XSRF-TOKEN",
        header_name="X-XSRF-TOKEN",
        cookie_path="/",
        cookie_samesite="strict",
        cookie_secure=settings.app.url_schema == "https",
        cookie_httponly=False,
        exclude=CSRF_EXCLUDED_PATHS,
    )


async def set_private_cache_control(message: Message, scope: Scope) -> None:
    if message["type"] != "http.response.start" or not PROTECTED_HTTP_PATH_PATTERN.match(
        scope["path"]
    ):
        return
    MutableScopeHeaders.from_message(message)["cache-control"] = "no-store"
