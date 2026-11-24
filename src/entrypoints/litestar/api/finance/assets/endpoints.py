from datetime import date, datetime
from typing import Annotated

from backend_sdk import Principal
from backend_sdk.integrations.litestar import AuthContext
from dishka import FromDishka
from litestar import Controller, Request, delete, get, patch, post, put
from litestar.datastructures import State
from litestar.di import NamedDependency, Provide
from litestar.params import PathParameter, QueryParameter

from core.finance.assets.analytics_use_cases import AssetAnalyticsUseCase
from core.finance.assets.enums import AssetSource
from core.finance.assets.goals import AssetGoalParams, SetAssetGoalParams
from core.finance.assets.reports import AssetReportParams
from core.finance.assets.schemas import (
    AssetMovementCommand,
    AssetMovementDeletion,
    AssetMovementsParams,
    AssetMovementUpdate,
    AssetOpeningPreviewParams,
    AssetRevisionsParams,
    CreateOverviewAsset,
)
from core.finance.assets.services import AssetMovementService
from core.finance.assets.valuation import AssetValuationParams
from core.finance.event_dispatchers import FinanceEventDispatcher
from entrypoints.litestar.api.finance.assets.dependencies import (
    parse_month,
    provide_cancel,
    provide_create_command,
    provide_positions,
    provide_report,
    provide_restore,
    provide_set_goal,
    provide_update_command,
)
from entrypoints.litestar.api.finance.assets.schemas import (
    ArchivePositionRequest,
    AssetGoalResponse,
    AssetGoalResult,
    AssetLocationRequest,
    AssetLocationResponse,
    AssetLocationsResponse,
    AssetMovementResponse,
    AssetMovementsResponse,
    AssetOpeningPreviewRequest,
    AssetOpeningPreviewResponse,
    AssetPositionRequest,
    AssetPositionResponse,
    AssetReportResponse,
    AssetRevisionResponse,
    AssetRevisionsResponse,
    AssetValuationResponse,
    OverviewAssetRequest,
)
from entrypoints.litestar.api.parameters import api_json_body


class FinanceAssetsController(Controller):
    path = "/finance/assets"
    tags = ["finance assets"]
    response_headers = {"Cache-Control": "no-store"}

    @post(
        "/opening-preview",
        status_code=200,
        summary="Preview an opening allocation",
        description=(
            "Compute the available budget after an opening allocation on its local date. "
            "Pass movementId to replace an existing movement in the calculation. "
            "Personal API token permissions: workspace.assets.read and workspace.finance.read."
        ),
        opt={
            "pat_permissions": ("workspace.assets.read", "workspace.finance.read"),
            "error_statuses": (400, 404, 409, 503),
        },
    )
    async def opening_preview(
        self,
        service: FromDishka[AssetMovementService],
        request: Request[Principal, AuthContext, State],
        current_datetime: FromDishka[datetime],
        data: Annotated[
            AssetOpeningPreviewRequest,
            api_json_body(
                title="Opening allocation preview",
                description="Date, position and budget-funded amount in the position currency.",
                examples=({"onDate": "2026-03-12", "positionId": "reserve", "amount": "100.00"},),
            ),
        ],
    ) -> AssetOpeningPreviewResponse:
        available, currency = await service.preview_opening(
            AssetOpeningPreviewParams(
                owner_username=request.user.username,
                now=current_datetime,
                on_date=data.on_date,
                position_id=data.position_id,
                amount=data.amount,
                movement_id=data.movement_id,
            ),
        )
        return AssetOpeningPreviewResponse(available_after=available, currency=currency)

    @get(
        "/positions",
        status_code=200,
        dependencies={"params": Provide(provide_positions, sync_to_thread=False)},
        summary="Value positions on a date",
        description=(
            "Read the known portfolio value, coverage and price sources. Personal API "
            "token permission: workspace.assets.read."
        ),
        opt={
            "pat_permissions": ("workspace.assets.read",),
            "error_statuses": (
                400,
                404,
            ),
        },
    )
    async def positions(
        self,
        use_case: FromDishka[AssetAnalyticsUseCase],
        params: NamedDependency[AssetValuationParams],
    ) -> AssetValuationResponse:
        return AssetValuationResponse.model_validate(await use_case.positions(params))

    @get(
        "/report",
        status_code=200,
        dependencies={"params": Provide(provide_report)},
        summary="Read the savings report",
        description=(
            "Evaluate the inclusive local date range in a single currency. Includes "
            "aggregate eligible income, the savings goal and a twelve-month forecast. "
            "Personal API token permission: workspace.assets.read."
        ),
        opt={
            "pat_permissions": ("workspace.assets.read",),
            "error_statuses": (
                400,
                404,
            ),
        },
    )
    async def report(
        self,
        use_case: FromDishka[AssetAnalyticsUseCase],
        params: NamedDependency[AssetReportParams],
    ) -> AssetReportResponse:
        return AssetReportResponse.model_validate(await use_case.report(params))

    @get(
        "/locations",
        status_code=200,
        summary="List asset locations",
        description=(
            "List accounts and storage locations owned by the principal. Personal API "
            "token permission: workspace.assets.read."
        ),
        opt={
            "pat_permissions": ("workspace.assets.read",),
            "error_statuses": (
                400,
                404,
            ),
        },
    )
    async def locations(
        self,
        use_case: FromDishka[AssetAnalyticsUseCase],
        request: Request[Principal, AuthContext, State],
    ) -> AssetLocationsResponse:
        rows = await use_case.locations(owner_username=request.user.username)
        return AssetLocationsResponse(
            items=[AssetLocationResponse.model_validate(row) for row in rows],
        )

    @post(
        "/locations",
        status_code=201,
        summary="Create location",
        description=(
            "Create location for the current owner. Personal API token permission: "
            "workspace.assets.create."
        ),
        opt={
            "pat_permissions": ("workspace.assets.create",),
            "error_statuses": (
                400,
                404,
                409,
            ),
        },
    )
    async def create_location(
        self,
        service: FromDishka[AssetMovementService],
        request: Request[Principal, AuthContext, State],
        data: Annotated[
            AssetLocationRequest,
            api_json_body(
                title="Create location",
                description="Metadata for a portfolio location.",
                examples=({"name": "Reserve"},),
            ),
        ],
    ) -> AssetLocationResponse:
        row = await service.create_location(
            owner_username=request.user.username,
            draft=data.to_domain_schema(),
        )
        return AssetLocationResponse.model_validate(row)

    @post(
        "/positions/overview",
        status_code=201,
        summary="Create an asset from the monthly overview",
        description=(
            "Create a position and optionally record its opening value in one transaction. "
            "An empty locationId selects or creates the named default location. Repeating the "
            "same requestId is idempotent. Personal API token permission: workspace.assets.create."
        ),
        opt={"pat_permissions": ("workspace.assets.create",), "error_statuses": (400, 404, 409)},
    )
    async def create_overview_asset(
        self,
        service: FromDishka[AssetMovementService],
        request: Request[Principal, AuthContext, State],
        current_datetime: FromDishka[datetime],
        data: Annotated[
            OverviewAssetRequest,
            api_json_body(
                title="New overview asset",
                description="Amount in the asset currency, independent of the budget.",
                examples=(
                    {
                        "requestId": "4fd38207-9c87-4671-931a-303141756680",
                        "position": {
                            "name": "Savings",
                            "kind": "bank",
                            "currency": "RUB",
                            "locationId": "",
                        },
                        "onDate": "2026-03-15",
                        "amount": "12000",
                        "defaultLocationName": "My assets",
                    },
                ),
            ),
        ],
    ) -> AssetPositionResponse:
        position = await service.create_overview_asset(
            CreateOverviewAsset(
                owner_username=request.user.username,
                now=current_datetime,
                source=AssetSource.PAT if request.auth.is_pat else AssetSource.WEB,
                can_write_budget=False,
                request_id=data.request_id,
                position=data.position.to_domain_schema(),
                on_date=data.on_date,
                amount=data.amount,
                default_location_name=data.default_location_name,
            ),
        )
        return AssetPositionResponse.model_validate(position)

    @patch(
        "/positions/{position_id:str}/archive",
        status_code=200,
        summary="Archive or restore an asset",
        description=(
            "Keep the position and its history while disabling new movements. "
            "Personal API token permission: workspace.assets.update."
        ),
        opt={"pat_permissions": ("workspace.assets.update",), "error_statuses": (400, 404)},
    )
    async def archive_position(
        self,
        service: FromDishka[AssetMovementService],
        request: Request[Principal, AuthContext, State],
        position_id: Annotated[
            str,
            PathParameter(
                description="Owned asset position identifier.",
                schema_extra={"examples": ["4e92d4de561f4bc7a3eed227868952db"]},
            ),
        ],
        data: Annotated[
            ArchivePositionRequest,
            api_json_body(
                title="Asset archive status",
                description="Set false to restore the position.",
                examples=({"archived": True},),
            ),
        ],
    ) -> AssetPositionResponse:
        position = await service.archive_position(
            owner_username=request.user.username,
            position_id=position_id,
            archived=data.archived,
        )
        return AssetPositionResponse.model_validate(position)

    @delete(
        "/positions/{position_id:str}",
        status_code=204,
        summary="Delete an unused asset",
        description=(
            "Permanently remove a position with no journal history. Returns 409 for a position "
            "referenced by any movement. Personal API token permission: workspace.assets.delete."
        ),
        opt={"pat_permissions": ("workspace.assets.delete",), "error_statuses": (400, 404, 409)},
    )
    async def delete_position(
        self,
        service: FromDishka[AssetMovementService],
        request: Request[Principal, AuthContext, State],
        position_id: Annotated[
            str,
            PathParameter(
                description="Owned asset position identifier.",
                schema_extra={"examples": ["4e92d4de561f4bc7a3eed227868952db"]},
            ),
        ],
    ) -> None:
        await service.delete_position(owner_username=request.user.username, position_id=position_id)

    @patch(
        "/locations/{location_id:str}",
        status_code=200,
        summary="Update location",
        description=(
            "Update location for the current owner. Personal API token permission: "
            "workspace.assets.update."
        ),
        opt={
            "pat_permissions": ("workspace.assets.update",),
            "error_statuses": (
                400,
                404,
                409,
            ),
        },
    )
    async def update_location(
        self,
        service: FromDishka[AssetMovementService],
        request: Request[Principal, AuthContext, State],
        location_id: Annotated[
            str,
            PathParameter(
                name="location_id",
                description="Owned location identifier.",
                schema_extra={"examples": ["4e92d4de561f4bc7a3eed227868952db"]},
            ),
        ],
        data: Annotated[
            AssetLocationRequest,
            api_json_body(
                title="Update location",
                description="Metadata for a portfolio location.",
                examples=({"name": "Reserve"},),
            ),
        ],
    ) -> AssetLocationResponse:
        row = await service.update_location(
            owner_username=request.user.username,
            location_id=location_id,
            draft=data.to_domain_schema(),
        )
        return AssetLocationResponse.model_validate(row)

    @post(
        "/positions",
        status_code=201,
        summary="Create position",
        description=(
            "Create position for the current owner. Personal API token permission: "
            "workspace.assets.create."
        ),
        opt={
            "pat_permissions": ("workspace.assets.create",),
            "error_statuses": (
                400,
                404,
                409,
            ),
        },
    )
    async def create_position(
        self,
        service: FromDishka[AssetMovementService],
        request: Request[Principal, AuthContext, State],
        data: Annotated[
            AssetPositionRequest,
            api_json_body(
                title="Create position",
                description="Metadata for a portfolio position.",
                examples=(
                    {
                        "name": "Cash reserve",
                        "kind": "cash",
                        "currency": "RUB",
                        "locationId": "4e92d4de561f4bc7a3eed227868952db",
                    },
                ),
            ),
        ],
    ) -> AssetPositionResponse:
        row = await service.create_position(
            owner_username=request.user.username,
            draft=data.to_domain_schema(),
        )
        return AssetPositionResponse.model_validate(row)

    @patch(
        "/positions/{position_id:str}",
        status_code=200,
        summary="Update position",
        description=(
            "Update an active position for the current owner. Restore an archived position "
            "before editing its details. Personal API token permission: "
            "workspace.assets.update."
        ),
        opt={
            "pat_permissions": ("workspace.assets.update",),
            "error_statuses": (
                400,
                404,
                409,
            ),
        },
    )
    async def update_position(
        self,
        service: FromDishka[AssetMovementService],
        request: Request[Principal, AuthContext, State],
        position_id: Annotated[
            str,
            PathParameter(
                name="position_id",
                description="Owned position identifier.",
                schema_extra={"examples": ["4e92d4de561f4bc7a3eed227868952db"]},
            ),
        ],
        data: Annotated[
            AssetPositionRequest,
            api_json_body(
                title="Update position",
                description="Metadata for a portfolio position.",
                examples=(
                    {
                        "name": "Cash reserve",
                        "kind": "cash",
                        "currency": "RUB",
                        "locationId": "4e92d4de561f4bc7a3eed227868952db",
                    },
                ),
            ),
        ],
    ) -> AssetPositionResponse:
        row = await service.update_position(
            owner_username=request.user.username,
            position_id=position_id,
            draft=data.to_domain_schema(),
        )
        return AssetPositionResponse.model_validate(row)

    @get(
        "/movements",
        status_code=200,
        summary="Read the movement journal",
        description=(
            "Read movement groups including canceled groups within optional inclusive "
            "dates. Personal API token permission: workspace.assets.read."
        ),
        opt={
            "pat_permissions": ("workspace.assets.read",),
            "error_statuses": (
                400,
                404,
            ),
        },
    )
    async def movements(
        self,
        use_case: FromDishka[AssetAnalyticsUseCase],
        request: Request[Principal, AuthContext, State],
        start: Annotated[
            date | None,
            QueryParameter(
                description="Inclusive start date.",
                schema_extra={"examples": ["2026-03-01"]},
            ),
        ] = None,
        end: Annotated[
            date | None,
            QueryParameter(
                description="Inclusive local end date.",
                schema_extra={"examples": ["2026-03-31"]},
            ),
        ] = None,
    ) -> AssetMovementsResponse:
        rows = await use_case.movements(
            AssetMovementsParams(owner_username=request.user.username, start=start, end=end),
        )
        return AssetMovementsResponse(
            items=[AssetMovementResponse.from_movement(row) for row in rows],
        )

    @get(
        "/movements/{movement_id:str}/revisions",
        status_code=200,
        summary="Read movement revisions",
        description=(
            "Read the immutable history of a movement group owned by the principal. "
            "Personal API token permission: workspace.assets.read."
        ),
        opt={
            "pat_permissions": ("workspace.assets.read",),
            "error_statuses": (
                400,
                404,
            ),
        },
    )
    async def revisions(
        self,
        use_case: FromDishka[AssetAnalyticsUseCase],
        request: Request[Principal, AuthContext, State],
        movement_id: Annotated[
            str,
            PathParameter(
                name="movement_id",
                description="Owned movement group identifier.",
                schema_extra={"examples": ["4e92d4de561f4bc7a3eed227868952db"]},
            ),
        ],
    ) -> AssetRevisionsResponse:
        rows = await use_case.revisions(
            AssetRevisionsParams(owner_username=request.user.username, movement_id=movement_id),
        )
        return AssetRevisionsResponse(
            items=[AssetRevisionResponse.from_domain_schema(row) for row in rows],
        )

    @post(
        "/movements",
        status_code=201,
        dependencies={"params": Provide(provide_create_command)},
        summary="Create an asset movement",
        description=(
            "Apply the entire movement atomically. Repeating a requestId with identical "
            "contents applies it once. A changed command returns 409. External deposits and "
            "withdrawals can specify enteredAmount and enteredCurrency. The saved rate for "
            "the movement date determines the amount in the position currency. "
            "Rate unavailability returns 503. Budget-affecting "
            "movements additionally require workspace.finance.create. Personal API token "
            "permission: workspace.assets.create."
        ),
        opt={
            "pat_permissions": ("workspace.assets.create",),
            "error_statuses": (
                400,
                404,
                409,
                503,
            ),
        },
    )
    async def create_movement(
        self,
        service: FromDishka[AssetMovementService],
        params: NamedDependency[AssetMovementCommand],
    ) -> AssetMovementResponse:
        return AssetMovementResponse.from_movement(await service.apply(params))

    @patch(
        "/movements/{movement_id:str}",
        status_code=200,
        dependencies={"params": Provide(provide_update_command)},
        summary="Correct an asset movement",
        description=(
            "Apply the change to the entire group, including its budget posting. A stale "
            "version returns 409. Corrections to an external deposit or withdrawal on the "
            "same date reuse its saved rate. Budget-affecting movements additionally require "
            "workspace.finance.update. Personal API token permission: "
            "workspace.assets.update."
        ),
        opt={
            "pat_permissions": ("workspace.assets.update",),
            "error_statuses": (
                400,
                404,
                409,
                503,
            ),
        },
    )
    async def correct_movement(
        self,
        service: FromDishka[AssetMovementService],
        params: NamedDependency[AssetMovementUpdate],
    ) -> AssetMovementResponse:
        return AssetMovementResponse.from_movement(await service.update_movement(params))

    @post(
        "/movements/{movement_id:str}/restore",
        status_code=200,
        dependencies={"params": Provide(provide_restore)},
        summary="Restore an asset movement",
        description=(
            "Apply the change to the entire group, including its budget posting. A stale "
            "version returns 409. Budget-affecting movements additionally require "
            "workspace.finance.update. Personal API token permission: "
            "workspace.assets.update."
        ),
        opt={
            "pat_permissions": ("workspace.assets.update",),
            "error_statuses": (
                400,
                404,
                409,
                503,
            ),
        },
    )
    async def restore_movement(
        self,
        service: FromDishka[AssetMovementService],
        params: NamedDependency[AssetMovementDeletion],
    ) -> AssetMovementResponse:
        return AssetMovementResponse.from_movement(await service.set_deleted(params))

    @delete(
        "/movements/{movement_id:str}",
        status_code=200,
        dependencies={"params": Provide(provide_cancel)},
        summary="Cancel an asset movement",
        description=(
            "Apply the change to the entire group, including its budget posting. A stale "
            "version returns 409. Budget-affecting movements additionally require "
            "workspace.finance.delete. Personal API token permission: "
            "workspace.assets.delete."
        ),
        opt={
            "pat_permissions": ("workspace.assets.delete",),
            "error_statuses": (
                400,
                404,
                409,
                503,
            ),
        },
    )
    async def cancel_movement(
        self,
        service: FromDishka[AssetMovementService],
        params: NamedDependency[AssetMovementDeletion],
    ) -> AssetMovementResponse:
        return AssetMovementResponse.from_movement(await service.set_deleted(params))

    @get(
        "/goals",
        status_code=200,
        summary="Read the effective savings goal",
        description=(
            "Read the most recent goal effective in the given month (YYYY-MM). Personal "
            "API token permission: workspace.assets.read."
        ),
        opt={
            "pat_permissions": ("workspace.assets.read",),
            "error_statuses": (
                400,
                404,
            ),
        },
    )
    async def goal(
        self,
        use_case: FromDishka[AssetAnalyticsUseCase],
        request: Request[Principal, AuthContext, State],
        month: Annotated[
            str,
            QueryParameter(
                pattern=r"^[0-9]{4}-[0-9]{2}$",
                description="Effective month (YYYY-MM).",
                schema_extra={"examples": ["2026-03"]},
            ),
        ],
    ) -> AssetGoalResult:
        goal = await use_case.goal(
            AssetGoalParams(owner_username=request.user.username, month=parse_month(month)),
        )
        return AssetGoalResult(
            goal=AssetGoalResponse.model_validate(goal) if goal is not None else None,
        )

    @put(
        "/goals/{month:str}",
        dependencies={"params": Provide(provide_set_goal, sync_to_thread=False)},
        status_code=200,
        summary="Set a monthly savings goal",
        description=(
            "Set the goal effective from YYYY-MM until the next saved version. Personal "
            "API token permission: workspace.assets.update."
        ),
        opt={
            "pat_permissions": ("workspace.assets.update",),
            "error_statuses": (
                400,
                404,
            ),
        },
    )
    async def set_goal(
        self,
        use_case: FromDishka[AssetAnalyticsUseCase],
        params: NamedDependency[SetAssetGoalParams],
        events: FromDishka[FinanceEventDispatcher],
        current_datetime: FromDishka[datetime],
    ) -> AssetGoalResult:
        goal = await use_case.set_goal(params)
        await events.check_asset_goal(owner_username=params.owner_username, now=current_datetime)
        return AssetGoalResult(goal=AssetGoalResponse.model_validate(goal))
