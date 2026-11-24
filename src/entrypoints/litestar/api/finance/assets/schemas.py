from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from core.finance.assets.enums import AssetMovementKind, AssetPositionKind, AssetSource
from core.finance.assets.goals import AssetGoal
from core.finance.assets.schemas import (
    AssetLocationDraft,
    AssetMovement,
    AssetMovementDraft,
    AssetMovementRevision,
    AssetPositionDraft,
)
from core.finance.enums import FinanceCurrency
from entrypoints.litestar.api.schemas import CamelCaseSchema


class AssetOpeningPreviewRequest(CamelCaseSchema):
    on_date: date
    position_id: str
    amount: Decimal = Field(
        ge=0,
        description="Opening allocation as a decimal string in the position currency.",
    )
    movement_id: str | None = Field(
        default=None,
        description="Owned movement being replaced, when editing.",
    )


class AssetOpeningPreviewResponse(CamelCaseSchema):
    available_after: Decimal
    currency: FinanceCurrency


class AssetLocationRequest(CamelCaseSchema):
    name: str = Field(min_length=1, max_length=255)

    def to_domain_schema(self) -> AssetLocationDraft:
        return AssetLocationDraft(name=self.name)


class AssetLocationResponse(AssetLocationRequest):
    id: str


class AssetLocationsResponse(CamelCaseSchema):
    items: list[AssetLocationResponse]


class AssetPositionRequest(AssetLocationRequest):
    location_id: str
    kind: AssetPositionKind
    currency: FinanceCurrency
    instrument: str = Field(default="", description="Instrument identifier for securities.")
    venue: str = Field(default="", description="Exchange or trading venue for securities.")
    annual_rate: Decimal | None = None
    matures_on: date | None = None

    def to_domain_schema(self) -> AssetPositionDraft:
        return AssetPositionDraft(**self.model_dump())


class AssetPositionResponse(AssetPositionRequest):
    id: str
    archived: bool


class OverviewAssetRequest(CamelCaseSchema):
    request_id: UUID
    position: AssetPositionRequest
    on_date: date
    amount: Decimal | None = Field(ge=0, default=None)
    default_location_name: str = Field(min_length=1, max_length=255)


class ArchivePositionRequest(CamelCaseSchema):
    archived: bool


class MovementFields(CamelCaseSchema):
    kind: AssetMovementKind
    on_date: date
    position_id: str
    counter_position_id: str | None = None
    external_funds: bool = Field(
        default=False,
        description=(
            "For buy or sell, set true if the money comes from or goes outside the tracker. "
            "Supply quantity and total trade amount in the security currency and omit "
            "counterPositionId. The trade counts toward net savings and leaves the budget intact. "
            "Otherwise buy and sell settle against a monetary position in the same currency."
        ),
    )
    amount: Decimal | None = Field(
        default=None,
        description=(
            "Cash amount in the position currency. For an external deposit or withdrawal, "
            "omit this field when supplying enteredAmount and enteredCurrency. If supplied "
            "alongside them, it must match the converted amount. Responses include the "
            "rounded amount credited or debited in the position currency."
        ),
    )
    entered_amount: Decimal | None = Field(
        default=None,
        gt=0,
        description=(
            "Original positive amount for an external deposit or withdrawal. "
            "Supply with enteredCurrency."
        ),
    )
    entered_currency: FinanceCurrency | None = Field(
        default=None,
        description=(
            "Original currency of enteredAmount. Both fields are null for entries "
            "recorded solely in the position currency through amount."
        ),
    )
    counter_amount: Decimal | None = Field(
        default=None,
        description="Cash received in the exchange destination currency.",
    )
    quantity: Decimal | None = Field(
        default=None,
        description="Number of securities as a decimal string.",
    )
    total_value: Decimal | None = Field(
        default=None,
        description="Value of the entire position on this date as a decimal string.",
    )
    category_id: str | None = None
    note: str = Field(default="", max_length=2000)

    def to_domain_schema(self) -> AssetMovementDraft:
        return AssetMovementDraft(**self.model_dump(include=set(MovementFields.model_fields)))


class AssetMovementCreateRequest(MovementFields):
    request_id: UUID


class AssetMovementUpdateRequest(MovementFields):
    version: int = Field(ge=1)


class AssetRevisionResponse(MovementFields):
    version: int
    deleted: bool
    source: AssetSource
    rate_set_id: str | None
    transaction_id: str | None
    changed_at: datetime

    @classmethod
    def from_domain_schema(cls, revision: AssetMovementRevision) -> AssetRevisionResponse:
        return cls(
            **asdict(revision.draft),
            version=revision.version,
            deleted=revision.deleted,
            source=revision.source,
            rate_set_id=revision.rate_set_id,
            transaction_id=revision.transaction_id,
            changed_at=revision.changed_at,
        )


class AssetMovementResponse(AssetRevisionResponse):
    id: str
    request_id: UUID
    created_at: datetime

    @classmethod
    def from_movement(cls, movement: AssetMovement) -> AssetMovementResponse:
        state = AssetRevisionResponse.from_domain_schema(movement)
        return cls(
            **state.model_dump(),
            id=movement.id,
            request_id=movement.request_id,
            created_at=movement.created_at,
        )


class AssetMovementsResponse(CamelCaseSchema):
    items: list[AssetMovementResponse]


class AssetRevisionsResponse(CamelCaseSchema):
    items: list[AssetRevisionResponse]


class AssetGoalRequest(CamelCaseSchema):
    percent: Decimal = Field(ge=0, le=100)
    all_income: bool
    category_ids: list[str]

    def for_month(self, month: date) -> AssetGoal:
        return AssetGoal(
            month=month,
            percent=self.percent,
            all_income=self.all_income,
            category_ids=tuple(self.category_ids),
        )


class AssetGoalResponse(AssetGoalRequest):
    month: date


class AssetGoalResult(CamelCaseSchema):
    goal: AssetGoalResponse | None


class AssetPositionValueResponse(CamelCaseSchema):
    id: str
    archived: bool
    location_id: str
    name: str
    kind: AssetPositionKind
    currency: FinanceCurrency
    instrument: str
    venue: str
    annual_rate: Decimal | None
    matures_on: date | None
    quantity: Decimal | None
    original_value: Decimal | None
    value: Decimal | None
    price_date: date | None
    price_source: str
    rate_date: date | None
    rate_source: str
    missing_price: bool
    missing_rate: bool
    stale: bool


class AssetValuationResponse(CamelCaseSchema):
    as_of: date
    currency: FinanceCurrency
    known_value: Decimal
    complete: bool
    positions: list[AssetPositionValueResponse]


class MonthlySavingsResponse(CamelCaseSchema):
    month: date
    income: Decimal
    net_savings: Decimal
    target_percent: Decimal | None
    target_amount: Decimal | None
    actual_percent: Decimal | None
    remaining: Decimal | None
    full: bool
    achieved: bool | None


class ForecastPointResponse(CamelCaseSchema):
    month: date
    actual: Decimal
    target: Decimal | None


class AssetForecastResponse(CamelCaseSchema):
    start_value: Decimal | None
    observation_months: list[date]
    available_on: date | None
    monthly_actual: Decimal | None
    monthly_target: Decimal | None
    points: list[ForecastPointResponse]


class CapitalPointResponse(CamelCaseSchema):
    on_date: date
    known_value: Decimal
    complete: bool


class AssetReportResponse(CamelCaseSchema):
    tracking_start: date | None = Field(description="First date of regular asset accounting.")
    start: date
    end: date
    coverage_start: date | None
    coverage_end: date | None
    currency: FinanceCurrency
    opening: AssetValuationResponse
    closing: AssetValuationResponse
    deposits: Decimal
    withdrawals: Decimal
    net_savings: Decimal
    income: Decimal
    target_amount: Decimal | None
    actual_percent: Decimal | None
    remaining: Decimal | None
    achieved_months: int
    eligible_months: int
    payouts: Decimal | None
    fees: Decimal | None
    initial_assets: Decimal | None
    reconciliation: Decimal | None
    revaluation: Decimal | None
    by_kind: dict[str, Decimal]
    by_location: dict[str, Decimal]
    by_currency: dict[str, Decimal]
    non_interest_value: Decimal
    non_interest_percent: Decimal | None
    months: list[MonthlySavingsResponse]
    history: list[CapitalPointResponse]
    forecast: AssetForecastResponse
