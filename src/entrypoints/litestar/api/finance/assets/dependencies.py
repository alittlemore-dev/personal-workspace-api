from datetime import date, datetime
from typing import Annotated

from backend_sdk import Principal
from backend_sdk.integrations.litestar import AuthContext
from dishka import FromDishka
from dishka.integrations.litestar import inject
from litestar import Request
from litestar.datastructures import State
from litestar.params import PathParameter, QueryParameter

from core.finance.assets.enums import AssetSource
from core.finance.assets.goals import SetAssetGoalParams
from core.finance.assets.reports import AssetReportParams
from core.finance.assets.schemas import (
    AssetMovementCommand,
    AssetMovementDeletion,
    AssetMovementUpdate,
)
from core.finance.assets.valuation import AssetValuationParams
from core.finance.enums import FinanceCurrency
from core.finance.exceptions import InvalidFinanceDataError
from entrypoints.litestar.api.finance.assets.schemas import (
    AssetGoalRequest,
    AssetMovementCreateRequest,
    AssetMovementUpdateRequest,
)
from entrypoints.litestar.api.finance.schemas import FinanceVersionRequest
from entrypoints.litestar.api.parameters import (
    FinanceCurrencyQuery,
    FinanceVersionQuery,
    api_json_body,
)

MOVEMENT_EXAMPLE = {
    "kind": "depositExternal",
    "positionId": "4e92d4de561f4bc7a3eed227868952db",
    "enteredAmount": "100.00",
    "enteredCurrency": "USD",
    "onDate": "2026-03-12",
}


def parse_currency(value: str) -> FinanceCurrency:
    try:
        return FinanceCurrency(value)
    except ValueError as exc:
        raise InvalidFinanceDataError from exc


def parse_month(value: str) -> date:
    try:
        month = date.fromisoformat(f"{value}-01")
    except ValueError as exc:
        raise InvalidFinanceDataError from exc
    if month.isoformat()[:7] != value:
        raise InvalidFinanceDataError
    return month


@inject
async def provide_report(
    request: Request[Principal, AuthContext, State],
    start: Annotated[
        date,
        QueryParameter(
            description="Inclusive local start date.",
            schema_extra={"examples": ["2026-03-01"]},
        ),
    ],
    end: Annotated[
        date,
        QueryParameter(
            description="Inclusive local end date.",
            schema_extra={"examples": ["2026-03-31"]},
        ),
    ],
    currency: FinanceCurrencyQuery,
    current_datetime: FromDishka[datetime],
) -> AssetReportParams:
    return AssetReportParams(
        owner_username=request.user.username,
        start=start,
        end=end,
        currency=parse_currency(currency),
        now=current_datetime,
    )


def provide_positions(
    request: Request[Principal, AuthContext, State],
    as_of: Annotated[
        date,
        QueryParameter(
            name="asOf",
            description="Inclusive portfolio valuation date.",
            schema_extra={"examples": ["2026-03-31"]},
        ),
    ],
    currency: FinanceCurrencyQuery,
) -> AssetValuationParams:
    return AssetValuationParams(
        owner_username=request.user.username,
        as_of=as_of,
        currency=parse_currency(currency),
    )


@inject
async def provide_create_command(
    request: Request[Principal, AuthContext, State],
    data: Annotated[
        AssetMovementCreateRequest,
        api_json_body(
            title="New asset movement",
            description="A group of postings with a unique owner-scoped replay key.",
            examples=({**MOVEMENT_EXAMPLE, "requestId": "cfc74a46-0807-493e-9f53-0cd5da684688"},),
        ),
    ],
    current_datetime: FromDishka[datetime],
) -> AssetMovementCommand:
    if data.kind.affects_budget:
        request.auth.require_permissions("workspace.finance.create")
    return AssetMovementCommand(
        owner_username=request.user.username,
        source=AssetSource.PAT if request.auth.is_pat else AssetSource.WEB,
        now=current_datetime,
        can_write_budget=request.auth.allows_permissions("workspace.finance.create"),
        request_id=data.request_id,
        draft=data.to_domain_schema(),
    )


@inject
async def provide_update_command(
    request: Request[Principal, AuthContext, State],
    movement_id: Annotated[
        str,
        PathParameter(
            name="movement_id",
            description="Owned movement group identifier.",
            schema_extra={"examples": ["4e92d4de561f4bc7a3eed227868952db"]},
        ),
    ],
    data: Annotated[
        AssetMovementUpdateRequest,
        api_json_body(
            title="Movement correction",
            description="Replace the postings of the supplied revision.",
            examples=({**MOVEMENT_EXAMPLE, "version": 1},),
        ),
    ],
    current_datetime: FromDishka[datetime],
) -> AssetMovementUpdate:
    if data.kind.affects_budget:
        request.auth.require_permissions("workspace.finance.update")
    return AssetMovementUpdate(
        owner_username=request.user.username,
        source=AssetSource.PAT if request.auth.is_pat else AssetSource.WEB,
        now=current_datetime,
        can_write_budget=request.auth.allows_permissions("workspace.finance.update"),
        movement_id=movement_id,
        version=data.version,
        draft=data.to_domain_schema(),
    )


@inject
async def provide_cancel(
    request: Request[Principal, AuthContext, State],
    movement_id: Annotated[
        str,
        PathParameter(
            name="movement_id",
            description="Owned movement group identifier.",
            schema_extra={"examples": ["4e92d4de561f4bc7a3eed227868952db"]},
        ),
    ],
    version: FinanceVersionQuery,
    current_datetime: FromDishka[datetime],
) -> AssetMovementDeletion:
    return AssetMovementDeletion(
        owner_username=request.user.username,
        source=AssetSource.PAT if request.auth.is_pat else AssetSource.WEB,
        now=current_datetime,
        can_write_budget=request.auth.allows_permissions("workspace.finance.delete"),
        movement_id=movement_id,
        version=version,
        deleted=True,
    )


@inject
async def provide_restore(
    request: Request[Principal, AuthContext, State],
    movement_id: Annotated[
        str,
        PathParameter(
            name="movement_id",
            description="Owned movement group identifier.",
            schema_extra={"examples": ["4e92d4de561f4bc7a3eed227868952db"]},
        ),
    ],
    data: Annotated[
        FinanceVersionRequest,
        api_json_body(
            title="Restore movement",
            description="Current version of the cancelled group.",
            examples=({"version": 2},),
        ),
    ],
    current_datetime: FromDishka[datetime],
) -> AssetMovementDeletion:
    return AssetMovementDeletion(
        owner_username=request.user.username,
        source=AssetSource.PAT if request.auth.is_pat else AssetSource.WEB,
        now=current_datetime,
        can_write_budget=request.auth.allows_permissions("workspace.finance.update"),
        movement_id=movement_id,
        version=data.version,
        deleted=False,
    )


def provide_set_goal(
    request: Request[Principal, AuthContext, State],
    month: Annotated[
        str,
        PathParameter(
            name="month",
            description="First effective month (YYYY-MM).",
            schema_extra={"examples": ["2026-03"]},
        ),
    ],
    data: Annotated[
        AssetGoalRequest,
        api_json_body(
            title="Savings goal",
            description="Percentage and stable income category selection.",
            examples=({"percent": "10", "allIncome": True, "categoryIds": []},),
        ),
    ],
) -> SetAssetGoalParams:
    return SetAssetGoalParams(
        owner_username=request.user.username,
        goal=data.for_month(parse_month(month)),
    )
