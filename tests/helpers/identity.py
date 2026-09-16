from litestar.types import ASGIApp, Receive, Scope, Send

from core.identity import UserIdentity


class TestIdentityMiddleware:
    __test__ = False

    def __init__(self, app: ASGIApp, user: UserIdentity) -> None:
        self.app = app
        self.user = user

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope["user"] = self.user
        scope["auth"] = None
        await self.app(scope, receive, send)
