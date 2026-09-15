from typing import Any

from dishka import FromDishka
from dishka.integrations.litestar import DishkaRouter
from litestar import Controller, Request, Response, get, post, status_codes

from core.auth.schemas import User
from core.auth.use_cases import LoginUseCase
from entrypoints.litestar.api.auth.schemas import LoginRequestSchema, UserResponseSchema


class AuthApiController(Controller):
    path = "/auth"
    tags = ["auth"]

    @post(
        "/login",
        description="Authenticate the configured owner and create a session.",
        name="auth-login-api-handler",
        status_code=status_codes.HTTP_200_OK,
    )
    async def login(
        self,
        data: LoginRequestSchema,
        request: Request[Any, Any, Any],
        use_case: FromDishka[LoginUseCase],
    ) -> UserResponseSchema:
        user = use_case.execute(params=data.to_domain_schema())
        request.set_session({"username": user.username})
        return UserResponseSchema.from_domain_schema(schema=user)

    @get(
        "/session",
        description="Get the authenticated owner session.",
        name="auth-session-api-handler",
        status_code=status_codes.HTTP_200_OK,
    )
    async def get_session(self, request: Request[User, Any, Any]) -> UserResponseSchema:
        return UserResponseSchema.from_domain_schema(schema=request.user)

    @post(
        "/logout",
        description="Clear the authenticated owner session.",
        name="auth-logout-api-handler",
        status_code=status_codes.HTTP_200_OK,
    )
    async def logout(self, request: Request[User, Any, Any]) -> Response[str]:
        request.clear_session()
        return Response(content="", status_code=status_codes.HTTP_200_OK)


api_router = DishkaRouter("", route_handlers=[AuthApiController])
