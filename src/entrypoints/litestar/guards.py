from litestar.connection import ASGIConnection
from litestar.exceptions import NotAuthorizedException
from litestar.handlers.base import BaseRouteHandler

from core.identity import UserIdentity


def require_authenticated_user(
    connection: ASGIConnection,
    _route_handler: BaseRouteHandler,
) -> None:
    user = connection.scope.get("user")
    if not isinstance(user, UserIdentity) or not user.username.strip():
        raise NotAuthorizedException
