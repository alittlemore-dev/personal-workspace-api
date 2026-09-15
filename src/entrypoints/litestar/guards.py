from litestar.connection import ASGIConnection
from litestar.exceptions import NotAuthorizedException
from litestar.handlers.base import BaseRouteHandler

from core.auth.schemas import User


def require_authenticated_user(
    connection: ASGIConnection,
    _route_handler: BaseRouteHandler,
) -> None:
    user = connection.scope.get("user")
    if not isinstance(user, User) or not user.username.strip():
        raise NotAuthorizedException
