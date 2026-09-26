import hmac
from datetime import datetime
from typing import Any

from backend_sdk import RoleEnum
from backend_sdk.integrations.litestar import RequireRole
from dishka import FromDishka
from dishka.integrations.litestar import DishkaRouter
from litestar import Controller, Request, delete, get, post, put, status_codes
from litestar.exceptions import HTTPException

from core.telegram.enums import TelegramConnectionState
from core.telegram.use_cases import TelegramUseCase
from entrypoints.litestar.api.telegram.schemas import (
    TelegramConnectionResponse,
    TelegramInvitationResponse,
    TelegramIssuedInvitationResponse,
    TelegramItemId,
    TelegramLabelRequest,
    TelegramSettingsResponse,
)
from infra.config.settings import settings


class TelegramApiController(Controller):
    path = "/telegram"
    tags = ["telegram"]
    include_in_schema = False
    response_headers = {"Cache-Control": "no-store"}
    guards = [RequireRole(RoleEnum.USER)]

    @get("", name="telegram-settings", status_code=status_codes.HTTP_200_OK)
    async def get_settings(
        self,
        request: Request,
        use_case: FromDishka[TelegramUseCase],
        current_datetime: FromDishka[datetime],
    ) -> TelegramSettingsResponse:
        owner = request.user.username
        return TelegramSettingsResponse(
            available=settings.telegram.available,
            invitations=[
                TelegramInvitationResponse.from_domain_schema(item)
                for item in await use_case.list_invitations(
                    owner_username=owner,
                    now=current_datetime,
                )
            ],
            connections=[
                TelegramConnectionResponse.from_domain_schema(item)
                for item in await use_case.list_connections(owner_username=owner)
            ],
        )

    @post(
        "/invitations",
        name="telegram-issue-invitation",
        status_code=status_codes.HTTP_201_CREATED,
    )
    async def create_invitation(
        self,
        data: TelegramLabelRequest,
        request: Request,
        use_case: FromDishka[TelegramUseCase],
        current_datetime: FromDishka[datetime],
    ) -> TelegramIssuedInvitationResponse:
        issued = await use_case.create_invitation(
            owner_username=request.user.username,
            label=data.label,
            now=current_datetime,
        )
        return TelegramIssuedInvitationResponse(url=issued.url, expires_at=issued.expires_at)

    @delete(
        "/invitations/{invitation_id:str}",
        name="telegram-cancel-invitation",
        status_code=status_codes.HTTP_204_NO_CONTENT,
    )
    async def cancel_invitation(
        self,
        invitation_id: TelegramItemId,
        request: Request,
        use_case: FromDishka[TelegramUseCase],
        current_datetime: FromDishka[datetime],
    ) -> None:
        await use_case.cancel_invitation(
            owner_username=request.user.username,
            invitation_id=invitation_id,
            now=current_datetime,
        )

    @post(
        "/connections/{connection_id:str}/approve",
        name="telegram-approve-connection",
        status_code=status_codes.HTTP_200_OK,
    )
    async def approve_connection(
        self,
        connection_id: TelegramItemId,
        request: Request,
        use_case: FromDishka[TelegramUseCase],
        current_datetime: FromDishka[datetime],
    ) -> TelegramConnectionResponse:
        return TelegramConnectionResponse.from_domain_schema(
            await use_case.approve_connection(
                owner_username=request.user.username,
                connection_id=connection_id,
                now=current_datetime,
            ),
        )

    @post(
        "/connections/{connection_id:str}/revoke",
        name="telegram-revoke-connection",
        status_code=status_codes.HTTP_200_OK,
    )
    async def revoke_connection(
        self,
        connection_id: TelegramItemId,
        request: Request,
        use_case: FromDishka[TelegramUseCase],
        current_datetime: FromDishka[datetime],
    ) -> TelegramConnectionResponse:
        return TelegramConnectionResponse.from_domain_schema(
            await use_case.change_connection_state(
                owner_username=request.user.username,
                connection_id=connection_id,
                state=TelegramConnectionState.REVOKED,
                now=current_datetime,
            ),
        )

    @post(
        "/connections/{connection_id:str}/block",
        name="telegram-block-connection",
        status_code=status_codes.HTTP_200_OK,
    )
    async def block_connection(
        self,
        connection_id: TelegramItemId,
        request: Request,
        use_case: FromDishka[TelegramUseCase],
        current_datetime: FromDishka[datetime],
    ) -> TelegramConnectionResponse:
        return TelegramConnectionResponse.from_domain_schema(
            await use_case.change_connection_state(
                owner_username=request.user.username,
                connection_id=connection_id,
                state=TelegramConnectionState.BLOCKED,
                now=current_datetime,
            ),
        )

    @post(
        "/connections/{connection_id:str}/unblock",
        name="telegram-unblock-connection",
        status_code=status_codes.HTTP_200_OK,
    )
    async def unblock_connection(
        self,
        connection_id: TelegramItemId,
        request: Request,
        use_case: FromDishka[TelegramUseCase],
        current_datetime: FromDishka[datetime],
    ) -> TelegramConnectionResponse:
        return TelegramConnectionResponse.from_domain_schema(
            await use_case.change_connection_state(
                owner_username=request.user.username,
                connection_id=connection_id,
                state=TelegramConnectionState.REVOKED,
                now=current_datetime,
            ),
        )

    @put("/connections/{connection_id:str}/label", name="telegram-rename-connection")
    async def rename_connection(
        self,
        connection_id: TelegramItemId,
        data: TelegramLabelRequest,
        request: Request,
        use_case: FromDishka[TelegramUseCase],
    ) -> TelegramConnectionResponse:
        return TelegramConnectionResponse.from_domain_schema(
            await use_case.rename_connection(
                owner_username=request.user.username,
                connection_id=connection_id,
                label=data.label,
            ),
        )


class TelegramWebhookController(Controller):
    path = "/telegram"
    include_in_schema = False
    opt = {"auth_public": True}

    @post("/webhook", name="telegram-webhook", status_code=200)
    async def receive_update(self, request: Request) -> dict[str, bool]:
        expected = settings.telegram.webhook_secret.get_secret_value()
        supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not expected or not hmac.compare_digest(supplied, expected):
            raise HTTPException(status_code=403)
        if not settings.telegram.available:
            raise HTTPException(status_code=503)
        update: Any = await request.json()
        if not isinstance(update, dict) or not isinstance(update.get("update_id"), int):
            raise HTTPException(status_code=400)
        await request.app.state.telegram_dispatcher.feed_raw_update(update)
        return {"ok": True}


api_router = DishkaRouter(
    path="",
    route_handlers=[TelegramApiController, TelegramWebhookController],
)
