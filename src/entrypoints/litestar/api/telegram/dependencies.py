from datetime import datetime
from typing import Annotated

from backend_sdk import Principal
from backend_sdk.integrations.litestar import AuthContext
from dishka import FromDishka
from dishka.integrations.litestar import inject
from litestar import Request
from litestar.datastructures import State

from core.telegram.enums import TelegramConnectionState
from core.telegram.schemas import (
    ApproveTelegramConnectionParams,
    CancelTelegramInvitationParams,
    ChangeTelegramConnectionStateParams,
    CreateTelegramInvitationParams,
    ListTelegramInvitationsParams,
    RenameTelegramConnectionParams,
    SetTelegramConnectionSettingsParams,
)
from entrypoints.litestar.api.parameters import api_json_body
from entrypoints.litestar.api.telegram.schemas import (
    TelegramConnectionSettingsRequest,
    TelegramItemId,
    TelegramLabelRequest,
)


@inject
async def provide_get_settings_params(
    request: Request[Principal, AuthContext, State],
    current_datetime: FromDishka[datetime],
) -> ListTelegramInvitationsParams:
    return ListTelegramInvitationsParams(
        owner_username=request.user.username,
        now=current_datetime,
    )


@inject
async def provide_create_invitation_params(
    data: Annotated[
        TelegramLabelRequest,
        api_json_body(
            title="Telegram connection label",
            description=("User-defined, nonblank label of up to 100 characters."),
            examples=({"label": "Family notifications"},),
        ),
    ],
    request: Request[Principal, AuthContext, State],
    current_datetime: FromDishka[datetime],
) -> CreateTelegramInvitationParams:
    return CreateTelegramInvitationParams(
        owner_username=request.user.username,
        label=data.label,
        now=current_datetime,
    )


@inject
async def provide_cancel_invitation_params(
    invitation_id: TelegramItemId,
    request: Request[Principal, AuthContext, State],
    current_datetime: FromDishka[datetime],
) -> CancelTelegramInvitationParams:
    return CancelTelegramInvitationParams(
        owner_username=request.user.username,
        invitation_id=invitation_id,
        now=current_datetime,
    )


@inject
async def provide_approve_connection_params(
    connection_id: TelegramItemId,
    request: Request[Principal, AuthContext, State],
    current_datetime: FromDishka[datetime],
) -> ApproveTelegramConnectionParams:
    return ApproveTelegramConnectionParams(
        owner_username=request.user.username,
        connection_id=connection_id,
        now=current_datetime,
    )


@inject
async def provide_revoke_connection_params(
    connection_id: TelegramItemId,
    request: Request[Principal, AuthContext, State],
    current_datetime: FromDishka[datetime],
) -> ChangeTelegramConnectionStateParams:
    return ChangeTelegramConnectionStateParams(
        owner_username=request.user.username,
        connection_id=connection_id,
        state=TelegramConnectionState.REVOKED,
        now=current_datetime,
    )


@inject
async def provide_block_connection_params(
    connection_id: TelegramItemId,
    request: Request[Principal, AuthContext, State],
    current_datetime: FromDishka[datetime],
) -> ChangeTelegramConnectionStateParams:
    return ChangeTelegramConnectionStateParams(
        owner_username=request.user.username,
        connection_id=connection_id,
        state=TelegramConnectionState.BLOCKED,
        now=current_datetime,
    )


@inject
async def provide_unblock_connection_params(
    connection_id: TelegramItemId,
    request: Request[Principal, AuthContext, State],
    current_datetime: FromDishka[datetime],
) -> ChangeTelegramConnectionStateParams:
    return ChangeTelegramConnectionStateParams(
        owner_username=request.user.username,
        connection_id=connection_id,
        state=TelegramConnectionState.REVOKED,
        now=current_datetime,
    )


def provide_rename_connection_params(
    connection_id: TelegramItemId,
    data: Annotated[
        TelegramLabelRequest,
        api_json_body(
            title="Telegram connection label",
            description=("User-defined, nonblank label of up to 100 characters."),
            examples=({"label": "Family notifications"},),
        ),
    ],
    request: Request[Principal, AuthContext, State],
) -> RenameTelegramConnectionParams:
    return RenameTelegramConnectionParams(
        owner_username=request.user.username,
        connection_id=connection_id,
        label=data.label,
    )


def provide_update_connection_settings_params(
    connection_id: TelegramItemId,
    data: Annotated[
        TelegramConnectionSettingsRequest,
        api_json_body(
            title="Telegram notification settings",
            description=(
                "Complete replacement of notification flags and the language for this connection."
            ),
            examples=(
                {
                    "notifyBirthday": True,
                    "notifyMemorableDate": True,
                    "notifyFinanceTransaction": True,
                    "notifyFinanceLimit": True,
                    "language": "en",
                },
            ),
        ),
    ],
    request: Request[Principal, AuthContext, State],
) -> SetTelegramConnectionSettingsParams:
    return SetTelegramConnectionSettingsParams(
        owner_username=request.user.username,
        connection_id=connection_id,
        settings=data.to_domain_schema(),
    )
