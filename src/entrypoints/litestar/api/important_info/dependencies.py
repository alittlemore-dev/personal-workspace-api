from typing import Annotated

from backend_sdk import Principal
from backend_sdk.integrations.litestar import AuthContext
from litestar import Request
from litestar.datastructures import State

from core.important_info.schemas import (
    CreateImportantInfoParams,
    ImportantInfoTargetParams,
    SetImportantInfoOrderParams,
    UpdateImportantInfoParams,
)
from entrypoints.litestar.api.important_info.schemas import (
    ImportantInfoOrderRequestSchema,
    ImportantInfoRequestSchema,
)
from entrypoints.litestar.api.parameters import ImportantInfoIdPath, api_json_body


def provide_create_item_params(
    data: Annotated[
        ImportantInfoRequestSchema,
        api_json_body(
            title="Private note",
            description="Single-line text, up to 255 characters.",
            examples=({"text": ("Passport renewal appointment on 25 October")},),
        ),
    ],
    request: Request[Principal, AuthContext, State],
) -> CreateImportantInfoParams:
    return CreateImportantInfoParams(
        text=data.text,
        author_username=request.user.username,
    )


def provide_set_order_params(
    data: Annotated[
        ImportantInfoOrderRequestSchema,
        api_json_body(
            title="Note display order",
            description=("Every current note identifier exactly once, in the requested order."),
            examples=(
                {"ids": ["4e92d4de561f4bc7a3eed227868952db", "1bb209e394954b71bd78b52d572dd835"]},
            ),
        ),
    ],
    request: Request[Principal, AuthContext, State],
) -> SetImportantInfoOrderParams:
    return SetImportantInfoOrderParams(
        ids=data.ids,
        author_username=request.user.username,
    )


def provide_update_item_params(
    item_id: ImportantInfoIdPath,
    data: Annotated[
        ImportantInfoRequestSchema,
        api_json_body(
            title="Private note",
            description="Single-line text, up to 255 characters.",
            examples=({"text": ("Passport renewal appointment on 25 October")},),
        ),
    ],
    request: Request[Principal, AuthContext, State],
) -> UpdateImportantInfoParams:
    return UpdateImportantInfoParams(
        item_id=item_id,
        text=data.text,
        author_username=request.user.username,
    )


def provide_delete_item_params(
    item_id: ImportantInfoIdPath,
    request: Request[Principal, AuthContext, State],
) -> ImportantInfoTargetParams:
    return ImportantInfoTargetParams(
        item_id=item_id,
        author_username=request.user.username,
    )
