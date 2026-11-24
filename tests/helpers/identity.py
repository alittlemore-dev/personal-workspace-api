from backend_sdk import Principal
from backend_sdk.integrations.litestar import AuthContext
from litestar.types import ASGIApp, Receive, Scope, Send


class TestIdentityMiddleware:
    __test__ = False

    def __init__(self, app: ASGIApp, user: Principal) -> None:
        self.app = app
        self.user = user

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope["user"] = self.user
        scope["auth"] = AuthContext(valid_for_seconds=300)
        await self.app(scope, receive, send)
