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
from entrypoints.litestar.api.parameters import ImportantInfoIdPath


def provide_create_item_params(
    data: ImportantInfoRequestSchema,
    request: Request[Principal, AuthContext, State],
) -> CreateImportantInfoParams:
    return CreateImportantInfoParams(
        text=data.text,
        author_username=request.user.username,
    )


def provide_set_order_params(
    data: ImportantInfoOrderRequestSchema,
    request: Request[Principal, AuthContext, State],
) -> SetImportantInfoOrderParams:
    return SetImportantInfoOrderParams(
        ids=data.ids,
        author_username=request.user.username,
    )


def provide_update_item_params(
    item_id: ImportantInfoIdPath,
    data: ImportantInfoRequestSchema,
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
