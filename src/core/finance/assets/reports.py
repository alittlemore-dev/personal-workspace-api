from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from core.finance.assets.enums import AssetMovementKind as Kind
from core.finance.assets.enums import AssetPositionKind
from core.finance.assets.goals import AssetGoal
from core.finance.assets.valuation import ZERO, AssetLedger, AssetValuation, PositionBalance
from core.finance.enums import FinanceCurrency
from core.finance.exceptions import InvalidFinanceDataError
from core.finance.schemas import Amount
from core.utils import next_month

DAY = timedelta(days=1)
FORECAST_MONTHS = 12
OBSERVATION_MONTHS = 3


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetReportParams:
    owner_username: str
    start: date
    end: date
    currency: FinanceCurrency
    now: datetime

    def __post_init__(self) -> None:
        if self.start > self.end or self.start == date.min or self.end.year == date.max.year:
            raise InvalidFinanceDataError


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetIncome:
    on_date: date
    category_id: str | None
    amount: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class MonthlySavings:
    month: date
    income: Decimal
    net_savings: Decimal
    target_percent: Decimal | None
    target_amount: Decimal | None
    actual_percent: Decimal | None
    remaining: Decimal | None
    full: bool
    achieved: bool | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ForecastPoint:
    month: date
    actual: Decimal
    target: Decimal | None


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetForecast:
    start_value: Decimal | None
    observation_months: list[date]
    available_on: date | None
    monthly_actual: Decimal | None
    monthly_target: Decimal | None
    points: list[ForecastPoint]


@dataclass(frozen=True, slots=True, kw_only=True)
class CapitalPoint:
    on_date: date
    known_value: Decimal
    complete: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetReport:
    tracking_start: date | None
    start: date
    end: date
    coverage_start: date | None
    coverage_end: date | None
    currency: FinanceCurrency
    opening: AssetValuation
    closing: AssetValuation
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
    months: list[MonthlySavings]
    history: list[CapitalPoint]
    forecast: AssetForecast


@dataclass(slots=True, kw_only=True)
class AssetReportFacts:
    zone: ZoneInfo
    incomes: list[AssetIncome]
    goals: list[AssetGoal]


@dataclass(slots=True, kw_only=True)
class AssetReportCalculator:
    ledger: AssetLedger
    facts: AssetReportFacts
    currency: FinanceCurrency
    today: date

    daily_flows: dict[date, list[tuple[Kind, Decimal | None]]] = field(init=False)

    def __post_init__(self) -> None:
        self.daily_flows = defaultdict(list)
        balances = {p.id: PositionBalance(position=p) for p in self.ledger.positions}
        for day in sorted(self.ledger.by_day):
            for movement in self.ledger.by_day[day]:
                draft = movement.draft
                if draft.kind == Kind.STATEMENT:
                    continue
                balance = balances[draft.position_id]
                previous = balance.quantity
                previous_price = balance.price
                self.ledger.apply(balances, movement)
                value = draft.amount if draft.amount is not None else draft.total_value
                if draft.kind == Kind.RECONCILE:
                    change = balance.quantity - previous
                    value = change
                    if balance.position.kind.security and change:
                        price = balance.price if balance.price is not None else previous_price
                        value = change * price if price is not None else None
                if value is not None:
                    value = self.ledger.rates.convert(
                        value,
                        balance.position.currency,
                        self.currency,
                        day,
                        movement.rate_set_id,
                    )
                kind = {
                    Kind.BUY_FROM_BUDGET: Kind.CONTRIBUTION,
                    Kind.DEPOSIT_EXTERNAL: Kind.CONTRIBUTION,
                    Kind.WITHDRAW_EXTERNAL: Kind.WITHDRAWAL,
                }.get(draft.kind, draft.kind)
                if draft.external_funds:
                    kind = Kind.CONTRIBUTION if draft.kind == Kind.BUY else Kind.WITHDRAWAL
                self.daily_flows[day].append((kind, value))

    def goal_at(self, day: date) -> AssetGoal | None:
        return max(
            (g for g in self.facts.goals if g.month <= day),
            key=lambda g: g.month,
            default=None,
        )

    def sum_income(self, start: date, end: date, goal: AssetGoal | None) -> Decimal:
        return Amount(
            sum(
                (
                    income.amount
                    for income in self.facts.incomes
                    if start <= income.on_date <= end
                    and (goal is None or goal.includes(income.category_id))
                ),
                ZERO,
            ),
        ).rounded(self.currency)

    def flows(self, start: date, end: date) -> dict[Kind, Decimal | None]:
        groups: dict[tuple[Kind, date | None], Decimal | None] = {}
        for day, entries in self.daily_flows.items():
            if start <= day <= end:
                for kind, value in entries:
                    # Budget transfer totals are rounded per month in the budget ledger.
                    month = day.replace(day=1) if kind.affects_budget else None
                    key = kind, month
                    accumulated = groups.get(key, ZERO)
                    groups[key] = (
                        accumulated + value
                        if value is not None and accumulated is not None
                        else None
                    )
        totals: dict[Kind, Decimal | None] = {}
        for (kind, _), value in groups.items():
            accumulated = totals.get(kind, ZERO)
            totals[kind] = (
                accumulated + Amount(value).rounded(self.currency)
                if value is not None and accumulated is not None
                else None
            )
        return totals

    def savings(self, flows: dict[Kind, Decimal | None]) -> tuple[Decimal, Decimal]:
        deposits = flows.get(Kind.CONTRIBUTION, ZERO)
        withdrawals = flows.get(Kind.WITHDRAWAL, ZERO)
        if deposits is None or withdrawals is None:
            # Budget postings always refer to a complete, persisted currency rate set.
            raise InvalidFinanceDataError
        return deposits, withdrawals

    def monthly(self, start: date, end: date, tracking: date) -> MonthlySavings:
        month = start.replace(day=1)
        goal = self.goal_at(start)
        income = self.sum_income(start, end, goal)
        deposits, withdrawals = self.savings(self.flows(start, end))
        net = deposits - withdrawals
        target = Amount(income * goal.percent / 100).rounded(self.currency) if goal else None
        full = (
            start == month
            and tracking <= start
            and end + DAY == next_month(month)
            and end < self.today
        )
        return MonthlySavings(
            month=month,
            full=full,
            income=income,
            net_savings=net,
            actual_percent=self.percent(net, income),
            target_percent=goal.percent if goal else None,
            target_amount=target,
            remaining=max(ZERO, target - net) if target is not None else None,
            achieved=net >= target if full and income > 0 and target is not None else None,
        )

    @staticmethod
    def percent(part: Decimal, total: Decimal) -> Decimal | None:
        return (part * 100 / total).quantize(Decimal("0.01")) if total > 0 else None

    def forecast(self, closing: AssetValuation) -> AssetForecast:
        tracking = self.ledger.tracking_start
        first_full = tracking if tracking is None or tracking.day == 1 else next_month(tracking)
        first_available = next_month(first_full) if first_full else None
        start_value = closing.known_value if closing.complete else None
        observed: list[date] = []
        day = min(closing.as_of, self.today)
        cursor = day.replace(day=1)
        if day < self.today and day + DAY == next_month(cursor):
            cursor = next_month(cursor)
        while first_full and cursor > first_full and len(observed) < OBSERVATION_MONTHS:
            cursor = (cursor - DAY).replace(day=1)
            observed.append(cursor)
        observed.reverse()
        goal = self.goal_at(day)
        actual_sum, income_sum = ZERO, ZERO
        for month in observed:
            end = next_month(month) - DAY
            deposits, withdrawals = self.savings(self.flows(month, end))
            actual_sum += deposits - withdrawals
            income_sum += self.sum_income(month, end, goal)
        count = len(observed)
        actual = Amount(actual_sum / count).rounded(self.currency) if count else None
        target = (
            Amount(income_sum * goal.percent / (100 * count)).rounded(self.currency)
            if count and goal
            else None
        )
        points: list[ForecastPoint] = []
        cursor = day.replace(day=1)
        if start_value is not None and actual is not None:
            for index in range(1, FORECAST_MONTHS + 1):
                cursor = next_month(cursor)
                points.append(
                    ForecastPoint(
                        month=cursor,
                        actual=start_value + index * actual,
                        target=start_value + index * target if target is not None else None,
                    ),
                )
        return AssetForecast(
            start_value=start_value,
            observation_months=observed,
            available_on=first_available,
            monthly_actual=actual,
            monthly_target=target,
            points=points,
        )

    def month_rows(self, start: date, end: date) -> list[MonthlySavings]:
        tracking = self.ledger.tracking_start
        if tracking is None:
            return []
        cursor = max(start, tracking)
        rows = []
        while cursor <= end:
            following = next_month(cursor)
            rows.append(self.monthly(cursor, min(end, following - DAY), tracking))
            cursor = following
        return rows

    def build(self, start: date, end: date) -> AssetReport:
        as_of = min(end, self.today)
        if start > as_of:
            raise InvalidFinanceDataError
        months = self.month_rows(start, as_of)
        flows = self.flows(start, as_of)
        deposits, withdrawals = self.savings(flows)
        net = deposits - withdrawals
        income = sum((m.income for m in months), ZERO)
        targets = [m.target_amount for m in months if m.target_amount is not None]
        target = sum(targets, ZERO) if targets else None
        history_dates = {day for day in self.ledger.by_day if start <= day <= as_of}
        history_dates.update(min(next_month(m.month) - DAY, as_of) for m in months)
        snapshots = self.ledger.snapshots(history_dates | {start - DAY, as_of}, self.currency)
        opening, closing = snapshots[start - DAY], snapshots[as_of]
        history = [
            CapitalPoint(
                on_date=day,
                known_value=snapshots[day].known_value,
                complete=snapshots[day].complete,
            )
            for day in sorted(history_dates)
        ]
        coverage_start = min(history_dates, default=None)
        coverage_end = max(history_dates, default=None)
        if months and self.ledger.tracking_start:
            coverage_start = min(coverage_start or start, max(start, self.ledger.tracking_start))
        by_kind: dict[str, Decimal] = defaultdict(Decimal)
        by_location: dict[str, Decimal] = defaultdict(Decimal)
        by_currency: dict[str, Decimal] = defaultdict(Decimal)
        for row in closing.positions:
            if row.value is not None:
                by_kind[row.kind] += row.value
                by_location[row.location_id] += row.value
                by_currency[row.currency] += row.value
        non_interest = sum(
            (
                by_kind.get(k, ZERO)
                for k in (
                    AssetPositionKind.CASH,
                    AssetPositionKind.BANK,
                    AssetPositionKind.BROKER_CASH,
                )
            ),
            ZERO,
        )
        payout, fees, correction = (
            flows.get(k, ZERO) for k in (Kind.PAYOUT, Kind.FEE, Kind.RECONCILE)
        )
        budget_opening, separate_opening = (
            flows.get(k, ZERO) for k in (Kind.OPENING_BUDGET, Kind.OPENING_EXTERNAL)
        )
        initial = (
            budget_opening + separate_opening
            if budget_opening is not None and separate_opening is not None
            else None
        )
        # A statement preceding the opening is an independent observation, not a posted balance.
        tracking = self.ledger.tracking_start
        opening_known = tracking is not None and (
            (opening.complete and opening.as_of >= tracking)
            or (start <= tracking <= as_of and min(self.ledger.by_day) == tracking)
        )
        change = None
        if (
            opening_known
            and closing.complete
            and payout is not None
            and fees is not None
            and correction is not None
            and initial is not None
        ):
            change = (
                closing.known_value
                - opening.known_value
                - net
                - payout
                + fees
                - correction
                - initial
            )
        return AssetReport(
            tracking_start=tracking,
            start=start,
            end=end,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            currency=self.currency,
            opening=opening,
            closing=closing,
            deposits=deposits,
            withdrawals=withdrawals,
            net_savings=net,
            income=income,
            target_amount=target,
            actual_percent=self.percent(net, income),
            remaining=max(ZERO, target - net) if target is not None else None,
            achieved_months=sum(m.achieved is True for m in months),
            eligible_months=sum(m.achieved is not None for m in months),
            payouts=payout,
            fees=fees,
            initial_assets=initial,
            reconciliation=correction,
            revaluation=change,
            by_kind=dict(by_kind),
            by_location=dict(by_location),
            by_currency=dict(by_currency),
            non_interest_value=non_interest,
            non_interest_percent=self.percent(non_interest, closing.known_value)
            if closing.complete
            else None,
            months=months,
            history=history,
            forecast=self.forecast(closing),
        )
