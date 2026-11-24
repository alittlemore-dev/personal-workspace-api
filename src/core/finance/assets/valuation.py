from abc import ABC, abstractmethod
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal

from core.finance.assets.enums import AssetMovementKind, AssetPositionKind
from core.finance.assets.schemas import AssetMovement, AssetPosition
from core.finance.enums import FinanceCurrency
from core.finance.exceptions import FinanceConflictError
from core.finance.schemas import Amount

ZERO = Decimal(0)
ONE = Decimal(1)


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetValuationParams:
    owner_username: str
    as_of: date
    currency: FinanceCurrency


@dataclass(frozen=True, slots=True, kw_only=True)
class DailyPrice:
    on_date: date
    source: str
    price: Decimal
    percent_of_face: bool = False
    face_value: Decimal | None = None
    includes_coupon: bool = True
    accrued_coupon: Decimal | None = None

    @property
    def unit_price(self) -> Decimal | None:
        amount = self.price
        if self.percent_of_face:
            if self.face_value is None:
                return None
            amount = self.face_value * amount / 100
        if not self.includes_coupon:
            if self.accrued_coupon is None:
                return None
            amount += self.accrued_coupon
        return amount

    def stale(self, last_completed_session: date) -> bool:
        return self.on_date < last_completed_session


class DailyPriceProvider(ABC):
    @abstractmethod
    async def close(self, *, instrument: str, venue: str, as_of: date) -> DailyPrice | None: ...

    @abstractmethod
    def last_completed_session(self, *, venue: str, as_of: date) -> date: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetRate:
    id: str
    source: str
    on_date: date
    rates: dict[FinanceCurrency, Decimal]

    def factor(self, source: FinanceCurrency, target: FinanceCurrency) -> Decimal | None:
        if source == target:
            return ONE
        if source not in self.rates or target not in self.rates:
            return None
        return self.rates[source] / self.rates[target]


@dataclass(slots=True, kw_only=True)
class AssetRates:
    ordered: list[AssetRate]
    dates: list[date] = field(init=False)
    by_id: dict[str, AssetRate] = field(init=False)

    def __post_init__(self) -> None:
        self.dates = [item.on_date for item in self.ordered]
        self.by_id = {item.id: item for item in self.ordered}

    def at(self, day: date) -> AssetRate | None:
        index = bisect_right(self.dates, day)
        return self.ordered[index - 1] if index else None

    def convert(
        self,
        value: Decimal,
        source: FinanceCurrency,
        target: FinanceCurrency,
        day: date,
        rate_set_id: str | None = None,
    ) -> Decimal | None:
        if source == target or not value:
            return value
        rate = self.by_id.get(rate_set_id) if rate_set_id else self.at(day)
        factor = rate.factor(source, target) if rate else None
        return None if factor is None else value * factor


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetPositionValue:
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


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetValuation:
    as_of: date
    currency: FinanceCurrency
    known_value: Decimal
    complete: bool
    positions: list[AssetPositionValue]


@dataclass(slots=True, kw_only=True)
class PositionBalance:
    position: AssetPosition
    quantity: Decimal = ZERO
    price: Decimal | None = None
    price_date: date | None = None
    price_source: str = ""
    whole_value: Decimal | None = None

    def mark(self, value: Decimal | None, on_date: date, source: str) -> None:
        if value is not None:
            if not self.position.kind.security:
                self.quantity = value
            self.whole_value = value
            self.price = value / self.quantity if self.quantity else None
            self.price_date = on_date
            self.price_source = source

    def move(self, delta: Decimal) -> None:
        if delta:
            self.whole_value = None
            self.quantity += delta

    @property
    def original_value(self) -> Decimal | None:
        if self.whole_value is not None:
            return self.whole_value
        if not self.position.kind.security or not self.quantity:
            return self.quantity
        return None if self.price is None else self.quantity * self.price

    def valued(self, day: date, currency: FinanceCurrency, rates: AssetRates) -> AssetPositionValue:
        position = self.position
        original = self.original_value
        rate = rates.at(day) if currency != position.currency else None
        value = (
            None if original is None else rates.convert(original, position.currency, currency, day)
        )
        return AssetPositionValue(
            id=position.id,
            archived=position.archived,
            location_id=position.location_id,
            name=position.name,
            kind=position.kind,
            currency=position.currency,
            instrument=position.instrument,
            venue=position.venue,
            annual_rate=position.annual_rate,
            matures_on=position.matures_on,
            quantity=None if position.kind == AssetPositionKind.OTHER else self.quantity,
            original_value=original,
            value=Amount(value).rounded(currency) if value is not None else None,
            price_date=self.price_date,
            price_source=self.price_source,
            rate_date=rate.on_date if rate else None,
            rate_source=rate.source if rate else "",
            missing_price=original is None,
            missing_rate=(self.quantity != 0 or bool(original))
            and currency != position.currency
            and (rate is None or rate.factor(position.currency, currency) is None),
            stale=False,
        )


@dataclass(slots=True, kw_only=True)
class AssetLedger:
    positions: list[AssetPosition]
    movements: list[AssetMovement]
    rates: AssetRates
    by_day: dict[date, list[AssetMovement]] = field(init=False)
    tracking_start: date | None = field(init=False)

    def __post_init__(self) -> None:
        self.by_day = defaultdict(list)
        regular = []
        for movement in self.movements:
            if not movement.deleted:
                self.by_day[movement.draft.on_date].append(movement)
                if movement.draft.kind != AssetMovementKind.STATEMENT:
                    regular.append(movement.draft.on_date)
        self.tracking_start = min(regular, default=None)
        kinds = {p.id: p.kind for p in self.positions}
        for rows in self.by_day.values():
            rows.sort(key=lambda m: self.order(m, kinds[m.draft.position_id]))

    def evaluate(self, day: date, currency: FinanceCurrency) -> AssetValuation:
        return self.snapshots({day}, currency)[day]

    def snapshots(self, dates: set[date], currency: FinanceCurrency) -> dict[date, AssetValuation]:
        if not dates:
            return {}
        balances = {p.id: PositionBalance(position=p) for p in self.positions}
        snapshots = {}
        max_date = max(dates)
        for day in sorted(dates | self.by_day.keys()):
            if day > max_date:
                break
            regular = self.tracking_start is not None and self.tracking_start <= day
            observed: dict[str, PositionBalance] = {}
            for movement in self.by_day.get(day, ()):
                draft = movement.draft
                if draft.kind != AssetMovementKind.STATEMENT:
                    self.apply(balances, movement)
                elif not regular:
                    balance = PositionBalance(position=balances[draft.position_id].position)
                    self.observe(balance, movement)
                    observed[draft.position_id] = balance
            if day in dates:
                historical = not regular
                rows = []
                for key, balance in balances.items():
                    row = observed.get(key, balance).valued(day, currency, self.rates)
                    if historical and key not in observed:
                        row = replace(row, quantity=None, original_value=None, value=None)
                    rows.append(row)
                snapshots[day] = AssetValuation(
                    as_of=day,
                    currency=currency,
                    known_value=sum((row.value for row in rows if row.value is not None), ZERO),
                    complete=all(row.value is not None for row in rows),
                    positions=rows,
                )
        return snapshots

    @staticmethod
    def order(
        movement: AssetMovement,
        position_kind: AssetPositionKind,
    ) -> tuple[int, datetime, bool, str]:
        kind = movement.draft.kind
        priority = 0
        if kind in {AssetMovementKind.OPENING_EXTERNAL, AssetMovementKind.OPENING_BUDGET}:
            priority = -1
        observed = (
            movement.changed_at
            if kind in {AssetMovementKind.RECONCILE, AssetMovementKind.VALUATION}
            else movement.created_at
        )
        return (
            priority,
            observed,
            kind == AssetMovementKind.VALUATION and position_kind.security,
            movement.id,
        )

    @staticmethod
    def observe(balance: PositionBalance, movement: AssetMovement) -> None:
        draft = movement.draft
        observed = draft.quantity if balance.position.kind.security else draft.amount
        value = draft.total_value if balance.position.kind.security else draft.amount
        if value is None and observed and not balance.quantity:
            value = balance.whole_value
        if observed is not None:
            balance.move(observed - balance.quantity)
        balance.mark(value, draft.on_date, "statement")

    @classmethod
    def validate_balances(
        cls,
        positions: list[AssetPosition],
        movements: list[AssetMovement],
        *,
        edited_id: str,
    ) -> None:
        balances = {p.id: PositionBalance(position=p) for p in positions}
        for movement in sorted(
            movements,
            key=lambda m: (
                m.draft.on_date,
                cls.order(m, balances[m.draft.position_id].position.kind),
            ),
        ):
            draft = movement.draft
            if movement.deleted or draft.kind == AssetMovementKind.STATEMENT:
                continue
            balance = balances[draft.position_id]
            if (
                (movement.id == edited_id or draft.external_funds)
                and draft.kind
                in {
                    AssetMovementKind.BUY,
                    AssetMovementKind.SELL,
                    AssetMovementKind.BUY_FROM_BUDGET,
                }
                and not balance.quantity
                and balance.whole_value
            ):
                raise FinanceConflictError
            cls.apply(balances, movement)
            for key in (draft.position_id, draft.counter_position_id):
                if key is not None and balances[key].quantity < 0:
                    raise FinanceConflictError

    @classmethod
    def apply(cls, balances: dict[str, PositionBalance], movement: AssetMovement) -> None:
        draft = movement.draft
        kind = draft.kind
        balance = balances[draft.position_id]
        amount = draft.amount or ZERO
        quantity = draft.quantity or ZERO
        if kind == AssetMovementKind.RECONCILE:
            cls.observe(balance, movement)
        elif kind == AssetMovementKind.VALUATION:
            balance.mark(draft.total_value, draft.on_date, "manual")
        elif kind in {AssetMovementKind.OPENING_EXTERNAL, AssetMovementKind.OPENING_BUDGET}:
            balance.move(quantity if balance.position.kind.security else amount)
            value = draft.total_value if balance.position.kind.security else balance.quantity
            balance.mark(value, draft.on_date, "opening")
        elif kind in {AssetMovementKind.TRANSFER, AssetMovementKind.EXCHANGE}:
            balance.move(-amount)
            if draft.counter_position_id is not None:
                balances[draft.counter_position_id].move(draft.counter_amount or amount)
        elif kind in {
            AssetMovementKind.BUY,
            AssetMovementKind.SELL,
            AssetMovementKind.BUY_FROM_BUDGET,
        }:
            sign = -ONE if kind == AssetMovementKind.SELL else ONE
            balance.move(sign * quantity)
            if quantity:
                balance.price, balance.price_date, balance.price_source = (
                    amount / quantity,
                    draft.on_date,
                    "trade",
                )
            if draft.counter_position_id is not None and kind != AssetMovementKind.BUY_FROM_BUDGET:
                balances[draft.counter_position_id].move(-sign * amount)
        elif kind in {
            AssetMovementKind.CONTRIBUTION,
            AssetMovementKind.DEPOSIT_EXTERNAL,
            AssetMovementKind.PAYOUT,
        }:
            balance.move(amount)
        elif kind in {
            AssetMovementKind.WITHDRAWAL,
            AssetMovementKind.WITHDRAW_EXTERNAL,
            AssetMovementKind.FEE,
        }:
            balance.move(-amount)
