import hmac
from typing import Any

from backend_sdk import Principal, RoleEnum
from backend_sdk.integrations.litestar import AuthContext, RequireRole
from dishka import FromDishka
from dishka.integrations.litestar import DishkaRouter
from litestar import Controller, Request, delete, get, post, put, status_codes
from litestar.datastructures import State
from litestar.di import (
    NamedDependency,
    Provide,
)
from litestar.exceptions import HTTPException

from core.telegram.enums import TelegramRuntimeStatus
from core.telegram.schemas import (
    ApproveTelegramConnectionParams,
    CancelTelegramInvitationParams,
    ChangeTelegramConnectionStateParams,
    CreateTelegramInvitationParams,
    ListTelegramInvitationsParams,
    RenameTelegramConnectionParams,
    SetTelegramConnectionSettingsParams,
)
from core.telegram.use_cases import TelegramUseCase
from entrypoints.litestar.api.telegram.dependencies import (
    provide_approve_connection_params,
    provide_block_connection_params,
    provide_cancel_invitation_params,
    provide_create_invitation_params,
    provide_get_settings_params,
    provide_rename_connection_params,
    provide_revoke_connection_params,
    provide_unblock_connection_params,
    provide_update_connection_settings_params,
)
from entrypoints.litestar.api.telegram.guards import require_ready_bot, require_telegram_service
from entrypoints.litestar.api.telegram.runtime import get_runtime_status
from entrypoints.litestar.api.telegram.schemas import (
    TelegramConnectionResponse,
    TelegramInvitationResponse,
    TelegramIssuedInvitationResponse,
    TelegramRuntimeStatusResponse,
    TelegramSettingsResponse,
)
from infra.config.settings import settings


class TelegramApiController(Controller):
    path = "/telegram"
    tags = ["telegram"]
    security = [{"bearerAuth": []}]
    response_headers = {"Cache-Control": "no-store"}
    guards = [RequireRole(RoleEnum.USER), require_ready_bot]

    @get(
        "",
        name="telegram-settings",
        status_code=status_codes.HTTP_200_OK,
        dependencies={
            "params": Provide(provide_get_settings_params),
        },
    )
    async def get_settings(
        self,
        request: Request[Principal, AuthContext, State],
        use_case: FromDishka[TelegramUseCase],
        params: NamedDependency[ListTelegramInvitationsParams],
    ) -> TelegramSettingsResponse:
        owner = request.user.username
        return TelegramSettingsResponse(
            available=settings.telegram.available,
            status=await get_runtime_status(request),
            invitations=[
                TelegramInvitationResponse.from_domain_schema(item)
                for item in await use_case.list_invitations(
                    params=params,
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
        dependencies={"params": Provide(provide_create_invitation_params)},
    )
    async def create_invitation(
        self,
        use_case: FromDishka[TelegramUseCase],
        params: NamedDependency[CreateTelegramInvitationParams],
    ) -> TelegramIssuedInvitationResponse:
        issued = await use_case.create_invitation(
            params=params,
        )
        return TelegramIssuedInvitationResponse(url=issued.url, expires_at=issued.expires_at)

    @delete(
        "/invitations/{invitation_id:str}",
        name="telegram-cancel-invitation",
        status_code=status_codes.HTTP_204_NO_CONTENT,
        dependencies={"params": Provide(provide_cancel_invitation_params)},
    )
    async def cancel_invitation(
        self,
        use_case: FromDishka[TelegramUseCase],
        params: NamedDependency[CancelTelegramInvitationParams],
    ) -> None:
        await use_case.cancel_invitation(
            params=params,
        )

    @post(
        "/connections/{connection_id:str}/approve",
        name="telegram-approve-connection",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_approve_connection_params)},
    )
    async def approve_connection(
        self,
        use_case: FromDishka[TelegramUseCase],
        params: NamedDependency[ApproveTelegramConnectionParams],
    ) -> TelegramConnectionResponse:
        return TelegramConnectionResponse.from_domain_schema(
            await use_case.approve_connection(
                params=params,
            ),
        )

    @post(
        "/connections/{connection_id:str}/revoke",
        name="telegram-revoke-connection",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_revoke_connection_params)},
    )
    async def revoke_connection(
        self,
        use_case: FromDishka[TelegramUseCase],
        params: NamedDependency[ChangeTelegramConnectionStateParams],
    ) -> TelegramConnectionResponse:
        return TelegramConnectionResponse.from_domain_schema(
            await use_case.change_connection_state(
                params=params,
            ),
        )

    @post(
        "/connections/{connection_id:str}/block",
        name="telegram-block-connection",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_block_connection_params)},
    )
    async def block_connection(
        self,
        use_case: FromDishka[TelegramUseCase],
        params: NamedDependency[ChangeTelegramConnectionStateParams],
    ) -> TelegramConnectionResponse:
        return TelegramConnectionResponse.from_domain_schema(
            await use_case.change_connection_state(
                params=params,
            ),
        )

    @post(
        "/connections/{connection_id:str}/unblock",
        name="telegram-unblock-connection",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_unblock_connection_params)},
    )
    async def unblock_connection(
        self,
        use_case: FromDishka[TelegramUseCase],
        params: NamedDependency[ChangeTelegramConnectionStateParams],
    ) -> TelegramConnectionResponse:
        return TelegramConnectionResponse.from_domain_schema(
            await use_case.change_connection_state(
                params=params,
            ),
        )

    @put(
        "/connections/{connection_id:str}/label",
        name="telegram-rename-connection",
        dependencies={
            "params": Provide(provide_rename_connection_params, sync_to_thread=False),
        },
    )
    async def rename_connection(
        self,
        use_case: FromDishka[TelegramUseCase],
        params: NamedDependency[RenameTelegramConnectionParams],
    ) -> TelegramConnectionResponse:
        return TelegramConnectionResponse.from_domain_schema(
            await use_case.rename_connection(
                params=params,
            ),
        )

    @put(
        "/connections/{connection_id:str}/settings",
        name="telegram-update-connection-settings",
        dependencies={
            "params": Provide(provide_update_connection_settings_params, sync_to_thread=False),
        },
    )
    async def update_connection_settings(
        self,
        use_case: FromDishka[TelegramUseCase],
        params: NamedDependency[SetTelegramConnectionSettingsParams],
    ) -> TelegramConnectionResponse:
        return TelegramConnectionResponse.from_domain_schema(
            await use_case.set_connection_settings(
                params=params,
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
        if settings.telegram.delivery_mode != "webhook":
            raise HTTPException(status_code=503)
        if await get_runtime_status(request) != TelegramRuntimeStatus.READY:
            raise HTTPException(status_code=503)
        update: Any = await request.json()
        if not isinstance(update, dict) or not isinstance(update.get("update_id"), int):
            raise HTTPException(status_code=400)
        await request.app.state.telegram_dispatcher.feed_raw_update(update)
        return {"ok": True}


class TelegramRuntimeController(Controller):
    path = "/internal/telegram"
    include_in_schema = False
    opt = {"auth_public": True}
    guards = [require_telegram_service]
    response_headers = {"Cache-Control": "no-store"}

    @get("/status", name="internal-telegram-runtime-status")
    async def get_status(self, request: Request) -> TelegramRuntimeStatusResponse:
        return TelegramRuntimeStatusResponse(status=await get_runtime_status(request))


api_router = DishkaRouter(
    path="",
    route_handlers=[TelegramApiController, TelegramWebhookController, TelegramRuntimeController],
)
