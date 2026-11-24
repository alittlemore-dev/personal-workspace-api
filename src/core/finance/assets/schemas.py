from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, time
from decimal import Decimal
from hashlib import sha256
from json import dumps
from uuid import UUID, uuid7
from zoneinfo import ZoneInfo

from core.finance.assets.enums import AssetMovementKind as Kind
from core.finance.assets.enums import AssetPositionKind, AssetSource
from core.finance.assets.exceptions import AssetPermissionError
from core.finance.enums import FinanceCurrency
from core.finance.exceptions import FinanceConflictError, InvalidFinanceDataError
from core.finance.schemas import Amount, FinanceMonth, FinanceRateSet, FinanceTracker

NAME_LIMIT = 255
NOTE_LIMIT = 2000


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetLocationDraft:
    name: str

    def validate(self) -> None:
        if not self.name.strip() or len(self.name) > NAME_LIMIT:
            raise InvalidFinanceDataError


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetLocation(AssetLocationDraft):
    id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetPositionDraft(AssetLocationDraft):
    location_id: str
    kind: AssetPositionKind
    currency: FinanceCurrency
    instrument: str
    venue: str
    annual_rate: Decimal | None
    matures_on: date | None

    def validate(self) -> None:
        AssetLocationDraft.validate(self)
        if any(len(field) > NAME_LIMIT for field in (self.instrument, self.venue)):
            raise InvalidFinanceDataError
        if self.kind.security and not (self.instrument.strip() and self.venue.strip()):
            raise InvalidFinanceDataError
        if self.kind == AssetPositionKind.OTHER and (
            self.instrument or self.venue or self.annual_rate is not None or self.matures_on
        ):
            raise InvalidFinanceDataError
        if self.annual_rate is not None:
            Amount(self.annual_rate).validate_range()
            if self.annual_rate < 0:
                raise InvalidFinanceDataError


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetPosition(AssetPositionDraft):
    id: str
    archived: bool

    def check_identity(self, replacement: AssetPositionDraft) -> None:
        if (self.currency, self.kind, self.instrument, self.venue) != (
            replacement.currency,
            replacement.kind,
            replacement.instrument,
            replacement.venue,
        ):
            raise FinanceConflictError


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetMovementDraft:
    kind: Kind
    on_date: date
    position_id: str
    counter_position_id: str | None
    amount: Decimal | None
    counter_amount: Decimal | None
    quantity: Decimal | None
    total_value: Decimal | None
    category_id: str | None
    note: str
    entered_amount: Decimal | None = None
    entered_currency: FinanceCurrency | None = None
    external_funds: bool = False

    @property
    def notifies(self) -> bool:
        return self.kind.notifies or self.external_funds

    def required_fields(self, position: AssetPosition) -> tuple[set[str], set[str]]:
        if self.kind in {Kind.BUY, Kind.SELL, Kind.BUY_FROM_BUDGET}:
            if not position.kind.security:
                raise InvalidFinanceDataError
            return {"amount", "quantity"}, set()
        if self.kind == Kind.VALUATION:
            return {"total_value"}, set()
        if self.kind in {
            Kind.OPENING_BUDGET,
            Kind.OPENING_EXTERNAL,
            Kind.STATEMENT,
            Kind.RECONCILE,
        }:
            if not position.kind.security:
                return {"amount"}, set()
            if self.kind == Kind.OPENING_BUDGET:
                return {"quantity", "total_value"}, set()
            return {"quantity"}, {"total_value"}
        if not position.kind.monetary and self.kind != Kind.PAYOUT_TO_BUDGET:
            raise InvalidFinanceDataError
        cash = {"amount", "counter_amount"} if self.kind == Kind.EXCHANGE else {"amount"}
        return cash, set()

    def validate_counter(self, position: AssetPosition, counter: AssetPosition | None) -> None:
        if self.external_funds:
            if self.kind not in {Kind.BUY, Kind.SELL} or counter is not None:
                raise InvalidFinanceDataError
            return
        paired = self.kind in {Kind.BUY, Kind.SELL, Kind.TRANSFER, Kind.EXCHANGE}
        if paired != (counter is not None):
            raise InvalidFinanceDataError
        if counter is not None and (
            position.id == counter.id
            or not counter.kind.monetary
            or (self.kind == Kind.EXCHANGE) == (position.currency == counter.currency)
        ):
            raise InvalidFinanceDataError

    def validate(self, position: AssetPosition, counter: AssetPosition | None) -> None:
        self.validate_counter(position, counter)
        if (self.entered_amount is None) != (self.entered_currency is None):
            raise InvalidFinanceDataError
        if self.entered_currency is not None and self.entered_amount is not None:
            if self.kind not in {Kind.DEPOSIT_EXTERNAL, Kind.WITHDRAW_EXTERNAL}:
                raise InvalidFinanceDataError
            self.entered_currency.validate_money(Amount(self.entered_amount), positive=True)
        if len(self.note) > NOTE_LIMIT or (
            self.category_id is not None and self.kind != Kind.PAYOUT_TO_BUDGET
        ):
            raise InvalidFinanceDataError
        required, optional = self.required_fields(position)
        fields = {
            key
            for key, value in (
                ("amount", self.amount if self.entered_amount is None else self.entered_amount),
                ("counter_amount", self.counter_amount),
                ("quantity", self.quantity),
                ("total_value", self.total_value),
            )
            if value is not None
        }
        if not required <= fields <= required | optional:
            raise InvalidFinanceDataError
        positive = self.kind not in {
            Kind.OPENING_EXTERNAL,
            Kind.OPENING_BUDGET,
            Kind.RECONCILE,
            Kind.STATEMENT,
            Kind.VALUATION,
        }
        for value, currency in (
            (self.amount, position.currency),
            (self.counter_amount, counter.currency if counter else position.currency),
            (self.total_value, position.currency),
        ):
            if value is not None:
                currency.validate_money(Amount(value), positive=positive)
        if self.quantity is not None:
            Amount(self.quantity).validate_range()
            if (
                self.quantity < 0
                or (positive and self.quantity == 0)
                or (self.quantity * 10**12) != (self.quantity * 10**12).to_integral_value()
            ):
                raise InvalidFinanceDataError

    def occurred_at(self, zone: ZoneInfo) -> datetime:
        return datetime.combine(self.on_date, time(12), tzinfo=zone)

    def in_position_currency(
        self,
        currency: FinanceCurrency,
        rate: FinanceRateSet,
    ) -> AssetMovementDraft:
        if self.entered_amount is None or self.entered_currency is None:
            return self
        amount = Amount(self.entered_amount).converted(
            currency,
            rate.conversion_factor(self.entered_currency, currency),
        )
        if amount == 0 or (self.amount is not None and self.amount != amount):
            raise InvalidFinanceDataError
        return replace(self, amount=amount)

    def matches_request(self, requested: AssetMovementDraft) -> bool:
        if self.entered_amount is not None and requested.amount is None:
            return replace(self, amount=None) == requested
        return self == requested

    @property
    def budget_amount(self) -> Decimal:
        value = self.amount if self.amount is not None else self.total_value
        if value is None:
            raise InvalidFinanceDataError
        return value


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetMovementsParams:
    owner_username: str
    start: date | None
    end: date | None


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetRevisionsParams:
    owner_username: str
    movement_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetOpeningPreviewParams:
    owner_username: str
    now: datetime
    on_date: date
    position_id: str
    amount: Decimal
    movement_id: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetWriteContext:
    owner_username: str
    source: AssetSource
    can_write_budget: bool
    now: datetime

    def check_permission(self, kind: Kind) -> None:
        if kind.affects_budget and not self.can_write_budget:
            raise AssetPermissionError


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetMovementCommand(AssetWriteContext):
    request_id: UUID
    draft: AssetMovementDraft


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateOverviewAsset(AssetWriteContext):
    request_id: UUID
    position: AssetPositionDraft
    on_date: date
    amount: Decimal | None
    default_location_name: str

    def signature(self) -> str:
        fields = [asdict(self.position), self.on_date, self.amount, self.default_location_name]
        return sha256(dumps(fields, sort_keys=True, default=str).encode()).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetMovementChange(AssetWriteContext):
    movement_id: str
    version: int


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetMovementUpdate(AssetMovementChange):
    draft: AssetMovementDraft


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetMovementDeletion(AssetMovementChange):
    deleted: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetMovementRevision:
    version: int
    deleted: bool
    draft: AssetMovementDraft
    rate_set_id: str | None
    transaction_id: str | None
    source: AssetSource
    changed_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetMovement(AssetMovementRevision):
    id: str
    request_id: UUID
    created_at: datetime

    def check_change(self, change: AssetMovementChange, tracker: FinanceTracker) -> None:
        change.check_permission(self.draft.kind)
        if self.version != change.version:
            raise FinanceConflictError
        current = tracker.current_period(change.now)
        if (
            self.draft.kind.affects_budget
            and self.draft.on_date.replace(day=1) != current
            and self.created_at.astimezone(tracker.time_zone).date().replace(day=1) != current
        ):
            raise FinanceConflictError

    @classmethod
    def create(
        cls,
        command: AssetMovementCommand,
    ) -> AssetMovement:
        return cls(
            id=uuid7().hex,
            request_id=command.request_id,
            version=1,
            deleted=False,
            draft=command.draft,
            rate_set_id=None,
            transaction_id=None,
            created_at=command.now,
            changed_at=command.now,
            source=command.source,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetBudgetPosting:
    category_id: str | None
    month: FinanceMonth
    rate_set_id: str
    amount_rub: Amount
    currency: FinanceCurrency
