from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Self, TypedDict
from zoneinfo import ZoneInfo

from core.finance.enums import (
    FinanceCurrency,
    FinanceEventKind,
    FinanceKind,
    FinanceLimitScope,
    FinanceRevisionAction,
    FinanceSource,
    FinanceStatisticsCurrency,
    FinanceStatisticsGranularity,
    FinanceStatisticsPeriod,
)
from core.finance.exceptions import (
    FinanceConflictError,
    FinanceNotFoundError,
    InvalidFinanceDataError,
)
from core.i18n.enums import LanguageEnum
from core.utils import next_month

MONEY_QUANTUM = {
    FinanceCurrency.AMD: Decimal(1),
    FinanceCurrency.RUB: Decimal("0.01"),
    FinanceCurrency.USD: Decimal("0.01"),
    FinanceCurrency.EUR: Decimal("0.01"),
}
CATEGORY_NAME_MAX_LENGTH = 255
TRANSACTION_DESCRIPTION_MAX_LENGTH = 2000
AMOUNT_MAX_INTEGER_DIGITS = 18


class Amount(Decimal):
    __slots__ = ()

    def validate_range(self) -> None:
        if not self.is_finite() or self.adjusted() >= AMOUNT_MAX_INTEGER_DIGITS:
            raise InvalidFinanceDataError

    def validate_precision(self, currency: FinanceCurrency) -> None:
        self.validate_range()
        try:
            if self % MONEY_QUANTUM[currency] != 0:
                raise InvalidFinanceDataError
        except InvalidOperation as error:
            raise InvalidFinanceDataError from error

    def rounded(self, currency: FinanceCurrency) -> Amount:
        return Amount(self.quantize(MONEY_QUANTUM[currency], rounding=ROUND_HALF_UP))

    def converted(self, currency: FinanceCurrency, factor: Decimal) -> Amount:
        converted = Amount(self * factor)
        converted.validate_range()
        rounded = converted.rounded(currency)
        rounded.validate_precision(currency)
        return rounded


class FinanceCategoryName(str):
    __slots__ = ()

    def __new__(cls, value: str) -> Self:
        normalized = " ".join(value.split())
        if (
            not normalized
            or len(normalized) > CATEGORY_NAME_MAX_LENGTH
            or len(normalized.casefold()) > CATEGORY_NAME_MAX_LENGTH
        ):
            raise InvalidFinanceDataError
        return super().__new__(cls, normalized)

    @property
    def normalized(self) -> str:
        return self.casefold()


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceCategory:
    id: str
    stable_id: str
    kind: FinanceKind
    name: FinanceCategoryName
    planned_amount: Amount | None
    actual_amount: Amount
    difference: Amount | None
    position: int
    archived: bool

    def check_active(self) -> None:
        if self.archived:
            raise FinanceConflictError

    def check_accepting_transaction(self, existing_category_id: str | None) -> None:
        if self.archived and self.id != existing_category_id:
            raise FinanceConflictError

    @classmethod
    def from_snapshot(
        cls,
        snapshot: FinanceCategorySnapshot,
        currency: FinanceCurrency,
        actual_amount: Amount,
    ) -> FinanceCategory:
        difference = (
            Amount(
                snapshot.planned_amount - actual_amount
                if snapshot.kind == FinanceKind.EXPENSE
                else actual_amount - snapshot.planned_amount,
            ).rounded(currency)
            if snapshot.planned_amount is not None
            else None
        )
        return cls(
            id=snapshot.id,
            stable_id=snapshot.stable_id,
            kind=snapshot.kind,
            name=snapshot.name,
            planned_amount=snapshot.planned_amount,
            actual_amount=actual_amount.rounded(currency),
            difference=difference,
            position=snapshot.position,
            archived=snapshot.archived,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceMonth:
    id: str
    tracker_id: str
    period_start: date
    time_zone: ZoneInfo
    currency: FinanceCurrency
    opening_balance: Amount
    actual_income: Amount
    actual_expense: Amount
    planned_income: Amount | None
    planned_expense: Amount | None
    closing_balance: Amount
    categories: list[FinanceCategory]

    @classmethod
    def compose(cls, snapshot: FinanceMonthSnapshot, actuals: FinanceActuals) -> FinanceMonth:
        categories = [
            FinanceCategory.from_snapshot(
                category,
                snapshot.currency,
                actuals.by_category.get(category.id, Amount(0)),
            )
            for category in snapshot.categories
        ]
        return cls(
            id=snapshot.id,
            tracker_id=snapshot.tracker_id,
            period_start=snapshot.period_start,
            time_zone=snapshot.time_zone,
            currency=snapshot.currency,
            opening_balance=snapshot.opening_balance,
            actual_income=actuals.income.rounded(snapshot.currency),
            actual_expense=actuals.expense.rounded(snapshot.currency),
            planned_income=snapshot.planned_total(FinanceKind.INCOME),
            planned_expense=snapshot.planned_total(FinanceKind.EXPENSE),
            closing_balance=Amount(
                snapshot.opening_balance + actuals.income - actuals.expense,
            ).rounded(snapshot.currency),
            categories=categories,
        )

    def check_transaction_period(self, period: date | None) -> None:
        if period is not None and period not in (
            self.period_start,
            (self.period_start - timedelta(days=1)).replace(day=1),
        ):
            raise FinanceConflictError

    def crossed_limits(
        self,
        before: FinanceMonth,
        transaction: FinanceTransaction,
    ) -> list[FinanceEventPayload]:
        limits = []
        for category in self.categories:
            if category.kind != FinanceKind.EXPENSE or category.planned_amount is None:
                continue
            previous = before.get_category(category.id)
            if previous.actual_amount <= category.planned_amount < category.actual_amount:
                limits.append(
                    FinanceLimit(
                        scope=FinanceLimitScope.CATEGORY,
                        category_id=category.id,
                        category_name=category.name,
                        planned=category.planned_amount,
                        actual=category.actual_amount,
                    ),
                )
        if (
            self.planned_expense is not None
            and before.actual_expense <= self.planned_expense < self.actual_expense
        ):
            limits.append(
                FinanceLimit(
                    scope=FinanceLimitScope.MONTH,
                    category_id=None,
                    category_name="",
                    planned=self.planned_expense,
                    actual=self.actual_expense,
                ),
            )
        return [FinanceEventPayload.for_limit(self, transaction, limit) for limit in limits]

    def get_category(self, category_id: str) -> FinanceCategory:
        for category in self.categories:
            if category.id == category_id:
                return category
        raise FinanceNotFoundError

    def check_category_name(
        self,
        kind: FinanceKind,
        name: FinanceCategoryName,
        excluded_id: str | None,
    ) -> None:
        if any(
            category.kind == kind
            and category.name.normalized == name.normalized
            and category.id != excluded_id
            for category in self.categories
        ):
            raise FinanceConflictError

    def next_category_position(self, kind: FinanceKind) -> int:
        return (
            max(
                (category.position for category in self.categories if category.kind == kind),
                default=-1,
            )
            + 1
        )

    def convert_amounts(
        self,
        currency: FinanceCurrency,
        factor: Decimal,
    ) -> FinanceCurrencyConversion:
        return FinanceCurrencyConversion(
            opening_balance=self.opening_balance.converted(currency, factor),
            plans={
                category.id: category.planned_amount.converted(currency, factor)
                for category in self.categories
                if category.planned_amount is not None
            },
        )

    def needs_budget_rate(self, currency: FinanceStatisticsCurrency) -> bool:
        return currency not in {FinanceStatisticsCurrency.MONTH, self.currency} and (
            self.opening_balance != 0
            or any(category.planned_amount for category in self.categories)
        )

    def statistics_projection(
        self,
        currency: FinanceCurrency,
        facts: list[FinanceStatisticsFact],
        rate: FinanceRateSet | None,
    ) -> FinanceMonth:
        factor = rate.conversion_factor(self.currency, currency) if rate is not None else Decimal(1)
        current = [
            fact
            for fact in facts
            if fact.occurred_at.astimezone(self.time_zone).date().replace(day=1)
            == self.period_start
        ]
        by_category = {
            category.id: Amount(
                sum(
                    (fact.amount for fact in current if fact.category_id == category.stable_id),
                    Amount(0),
                ),
            )
            for category in self.categories
        }
        return FinanceMonth.compose(
            FinanceMonthSnapshot(
                id=self.id,
                tracker_id=self.tracker_id,
                period_start=self.period_start,
                time_zone=self.time_zone,
                currency=currency,
                opening_balance=self.opening_balance.converted(currency, factor),
                categories=[
                    FinanceCategorySnapshot(
                        id=row.id,
                        stable_id=row.stable_id,
                        kind=row.kind,
                        name=row.name,
                        planned_amount=row.planned_amount.converted(currency, factor)
                        if row.planned_amount is not None
                        else None,
                        position=row.position,
                        archived=row.archived,
                    )
                    for row in self.categories
                ],
            ),
            FinanceActuals(
                income=Amount(
                    sum(
                        (fact.amount for fact in current if fact.kind == FinanceKind.INCOME),
                        Amount(0),
                    ),
                ),
                expense=Amount(
                    sum(
                        (fact.amount for fact in current if fact.kind == FinanceKind.EXPENSE),
                        Amount(0),
                    ),
                ),
                by_category=by_category,
            ),
        )

    def amount_snapshot(self) -> FinanceCurrencyConversion:
        return FinanceCurrencyConversion(
            opening_balance=self.opening_balance,
            plans={
                category.id: category.planned_amount
                for category in self.categories
                if category.planned_amount is not None
            },
        )

    def rollover(self, excluded_stable_ids: set[str]) -> FinanceMonthRollover:
        self.closing_balance.validate_precision(self.currency)
        return FinanceMonthRollover(
            period_start=next_month(self.period_start),
            currency=self.currency,
            opening_balance=self.closing_balance,
            previous_month_id=self.id,
            categories=[
                category
                for category in self.categories
                if not category.archived and category.stable_id not in excluded_stable_ids
            ],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceCategorySnapshot:
    id: str
    stable_id: str
    kind: FinanceKind
    name: FinanceCategoryName
    planned_amount: Amount | None
    position: int
    archived: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceMonthSnapshot:
    id: str
    tracker_id: str
    period_start: date
    time_zone: ZoneInfo
    currency: FinanceCurrency
    opening_balance: Amount
    categories: list[FinanceCategorySnapshot]

    def planned_total(self, kind: FinanceKind) -> Amount | None:
        active = [
            category
            for category in self.categories
            if category.kind == kind and not category.archived
        ]
        if any(category.planned_amount is None for category in active):
            return None
        return Amount(sum((category.planned_amount or Amount(0) for category in active), Amount(0)))


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceActuals:
    income: Amount
    expense: Amount
    by_category: dict[str, Amount]


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceCurrencyConversion:
    opening_balance: Amount
    plans: dict[str, Amount]


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceMonthRollover:
    period_start: date
    currency: FinanceCurrency
    opening_balance: Amount
    previous_month_id: str
    categories: list[FinanceCategory]


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceTemplateCategory:
    kind: FinanceKind
    name: FinanceCategoryName
    position: int


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceTracker:
    id: str
    time_zone: ZoneInfo

    def current_period(self, now: datetime) -> date:
        local = now.astimezone(self.time_zone)
        return date(local.year, local.month, 1)


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceTransactionDraft:
    category_id: str
    amount: Amount
    currency: FinanceCurrency
    occurred_at: datetime
    description: str

    def validate(self, *, period_start: date, time_zone: ZoneInfo) -> None:
        self.validate_values()
        local_date = self.occurred_at.astimezone(time_zone).date()
        if local_date.year != period_start.year or local_date.month != period_start.month:
            raise InvalidFinanceDataError

    def validate_values(self) -> None:
        self.currency.validate_money(self.amount, positive=True)
        if self.occurred_at.tzinfo is None:
            raise InvalidFinanceDataError
        if len(self.description) > TRANSACTION_DESCRIPTION_MAX_LENGTH:
            raise InvalidFinanceDataError


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceTransaction:
    created_at: datetime
    source: FinanceSource
    author_id: str
    author_label: str
    id: str
    category_id: str | None
    category_name: str
    kind: FinanceKind
    amount: Amount
    currency: FinanceCurrency
    converted_amount: Amount
    occurred_at: datetime
    description: str
    rate_effective_on: date
    version: int
    deleted: bool
    pricing: FinanceTransactionPricing

    def check_writable(self, month: FinanceMonth, now: datetime) -> None:
        current = now.astimezone(month.time_zone).date().replace(day=1)
        if month.period_start != current and (
            next_month(month.period_start) != current
            or self.created_at.astimezone(month.time_zone).date().replace(day=1) != current
        ):
            raise FinanceConflictError

    def validate_update(self, draft: FinanceTransactionDraft, month: FinanceMonth) -> None:
        if draft.occurred_at == self.occurred_at:
            draft.validate_values()
        else:
            draft.validate(period_start=month.period_start, time_zone=month.time_zone)

    def check_updatable(self, version: int) -> None:
        if self.version != version or self.deleted:
            raise FinanceConflictError

    def has_monetary_change(self, draft: FinanceTransactionDraft, time_zone: ZoneInfo) -> bool:
        return (
            self.amount != draft.amount
            or self.currency != draft.currency
            or self.occurred_at.astimezone(time_zone).date()
            != draft.occurred_at.astimezone(time_zone).date()
        )

    def check_deletion_change(self, version: int, *, deleted: bool) -> None:
        if self.version != version or self.deleted == deleted:
            raise FinanceConflictError

    def snapshot(self) -> FinanceTransactionSnapshot:
        return {
            "categoryId": self.category_id,
            "kind": self.kind.value,
            "amount": str(self.amount),
            "currency": self.currency.value,
            "amountRub": str(self.pricing.amount_rub),
            "rateSetId": self.pricing.rate_set_id,
            "occurredAt": self.occurred_at.isoformat(),
            "description": self.description,
            "version": self.version,
            "deleted": self.deleted,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceTransactionPricing:
    rate_set_id: str
    amount_rub: Amount

    @classmethod
    def from_draft(
        cls,
        draft: FinanceTransactionDraft,
        rate_set_id: str,
        rate_set: FinanceRateSet,
    ) -> FinanceTransactionPricing:
        amount_rub = Amount(draft.amount * rate_set.rates[draft.currency])
        amount_rub.validate_range()
        return cls(
            rate_set_id=rate_set_id,
            amount_rub=amount_rub,
        )


class FinanceTransactionSnapshot(TypedDict):
    categoryId: str | None
    kind: str
    amount: str
    currency: str
    amountRub: str
    rateSetId: str
    occurredAt: str
    description: str
    version: int
    deleted: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceTransactionRevision:
    number: int
    action: FinanceRevisionAction
    previous_state: FinanceTransactionSnapshot
    actor_username: str
    changed_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceRateSet:
    effective_on: date
    fetched_at: datetime
    rates: dict[FinanceCurrency, Decimal]
    nominals: dict[FinanceCurrency, int]
    payload_hash: str

    def conversion_factor(self, source: FinanceCurrency, target: FinanceCurrency) -> Decimal:
        return self.rates[source] / self.rates[target]


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceCurrencyChange:
    month_id: str
    time_zone: ZoneInfo
    previous_currency: FinanceCurrency
    new_currency: FinanceCurrency
    rate_set_id: str
    before: FinanceCurrencyConversion
    after: FinanceCurrencyConversion
    actor_username: str
    now: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceTransactions:
    transactions: list[FinanceTransaction]


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceRevisions:
    revisions: list[FinanceTransactionRevision]


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceMonthParams:
    owner_username: str
    now: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class EnsureFinanceMonthParams(FinanceMonthParams):
    time_zone: ZoneInfo
    language: LanguageEnum


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateOpeningBalanceParams(FinanceMonthParams):
    amount: Amount


@dataclass(frozen=True, slots=True, kw_only=True)
class ChangeFinanceCurrencyParams(FinanceMonthParams):
    currency: FinanceCurrency


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateFinanceCategoryParams(FinanceMonthParams):
    kind: FinanceKind
    name: FinanceCategoryName
    planned_amount: Amount | None

    def validate(self, currency: FinanceCurrency) -> None:
        if self.planned_amount is not None:
            currency.validate_money(self.planned_amount, positive=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateFinanceCategoryParams(FinanceMonthParams):
    category_id: str
    name: FinanceCategoryName
    planned_amount: Amount | None
    position: int

    def validate(self, currency: FinanceCurrency) -> None:
        if self.planned_amount is not None:
            currency.validate_money(self.planned_amount, positive=False)
        if self.position < 0:
            raise InvalidFinanceDataError


@dataclass(frozen=True, slots=True, kw_only=True)
class SetFinanceCategoryArchivedParams(FinanceMonthParams):
    category_id: str
    archived: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteFinanceCategoryParams(FinanceMonthParams):
    category_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ListFinanceTransactionsParams(FinanceMonthParams):
    include_deleted: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceActor:
    source: FinanceSource
    identifier: str
    label: str
    connection_id: str
    telegram_user_id: int | None
    private_chat_id: int | None
    operation_id: str
    month_id: str

    @classmethod
    def web(cls, owner_username: str) -> FinanceActor:
        return cls(
            source=FinanceSource.WEB,
            identifier=owner_username,
            label=owner_username,
            connection_id="",
            telegram_user_id=None,
            private_chat_id=None,
            operation_id="",
            month_id="",
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class TelegramFinanceContextParams:
    telegram_user_id: int
    private_chat_id: int
    now: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateFinanceTransactionParams(FinanceMonthParams):
    period_start: date | None
    draft: FinanceTransactionDraft
    actor: FinanceActor


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateFinanceTransactionParams(FinanceMonthParams):
    period_start: date | None
    transaction_id: str
    draft: FinanceTransactionDraft
    version: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SetFinanceTransactionDeletedParams(FinanceMonthParams):
    period_start: date | None
    transaction_id: str
    version: int
    deleted: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceTransactionRevisionsParams(FinanceMonthParams):
    transaction_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceOpeningBalanceUpdate:
    month: FinanceMonth
    params: UpdateOpeningBalanceParams


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceCategoryCreation:
    month: FinanceMonth
    params: CreateFinanceCategoryParams
    position: int


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceCategoryUpdate:
    month: FinanceMonth
    category: FinanceCategory
    params: UpdateFinanceCategoryParams


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceCategoryArchival:
    month: FinanceMonth
    category: FinanceCategory
    params: SetFinanceCategoryArchivedParams


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceCategoryDeletion:
    month: FinanceMonth
    category: FinanceCategory


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceTransactionCreation:
    month: FinanceMonth
    category: FinanceCategory
    params: CreateFinanceTransactionParams
    pricing: FinanceTransactionPricing


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceTransactionUpdate:
    month: FinanceMonth
    category: FinanceCategory
    transaction: FinanceTransaction
    params: UpdateFinanceTransactionParams
    pricing: FinanceTransactionPricing | None


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceTransactionDeletionChange:
    month: FinanceMonth
    transaction: FinanceTransaction
    params: SetFinanceTransactionDeletedParams

    @property
    def action(self) -> FinanceRevisionAction:
        return (
            FinanceRevisionAction.DELETE if self.params.deleted else FinanceRevisionAction.RESTORE
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceEventPayload:
    month_id: str
    period_start: date
    transaction_id: str
    transaction_version: int
    author_id: str
    author_label: str
    source: str
    kind: FinanceKind
    amount: Amount
    currency: FinanceCurrency
    category_id: str | None
    category_name: str
    limit_scope: FinanceLimitScope
    planned_amount: Amount | None
    actual_amount: Amount | None

    @classmethod
    def for_limit(
        cls,
        month: FinanceMonth,
        transaction: FinanceTransaction,
        limit: FinanceLimit,
    ) -> FinanceEventPayload:
        return cls(
            month_id=month.id,
            period_start=month.period_start,
            transaction_id=transaction.id,
            transaction_version=transaction.version,
            author_id=transaction.author_id,
            author_label=transaction.author_label,
            source=transaction.source.value,
            kind=FinanceKind.EXPENSE,
            amount=transaction.amount,
            currency=month.currency,
            category_id=limit.category_id,
            category_name=limit.category_name,
            limit_scope=limit.scope,
            planned_amount=limit.planned,
            actual_amount=limit.actual,
        )

    @classmethod
    def for_transaction(
        cls,
        month: FinanceMonth,
        transaction: FinanceTransaction,
    ) -> FinanceEventPayload:
        return cls(
            month_id=month.id,
            period_start=month.period_start,
            transaction_id=transaction.id,
            transaction_version=transaction.version,
            author_id=transaction.author_id,
            author_label=transaction.author_label,
            source=transaction.source.value,
            kind=transaction.kind,
            amount=transaction.amount,
            currency=transaction.currency,
            category_id=transaction.category_id,
            category_name=transaction.category_name,
            limit_scope=FinanceLimitScope.CATEGORY,
            planned_amount=None,
            actual_amount=None,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceEvent:
    owner_username: str
    kind: FinanceEventKind
    payload: FinanceEventPayload
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceEventConfig:
    lifetime: timedelta


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceLimit:
    scope: FinanceLimitScope
    category_id: str | None
    category_name: str
    planned: Amount
    actual: Amount


@dataclass(frozen=True, slots=True, kw_only=True)
class ConfirmedFinanceOperationParams:
    actor: FinanceActor
    owner_username: str
    now: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceHistoricalMonthParams(FinanceMonthParams):
    period_start: date

    def check_period(self, month: FinanceMonth) -> None:
        if self.period_start.day != 1 or self.period_start > month.period_start:
            raise InvalidFinanceDataError


@dataclass(frozen=True, slots=True, kw_only=True)
class ListHistoricalFinanceTransactionsParams(FinanceHistoricalMonthParams):
    include_deleted: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class HistoricalFinanceRevisionsParams(FinanceHistoricalMonthParams):
    transaction_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceStatisticsParams(FinanceMonthParams):
    period: FinanceStatisticsPeriod
    currency: FinanceStatisticsCurrency


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceStatisticsWindow:
    start: datetime
    end: datetime
    granularity: FinanceStatisticsGranularity

    @classmethod
    def for_period(
        cls,
        period: FinanceStatisticsPeriod,
        now: datetime,
        time_zone: ZoneInfo,
    ) -> tuple[FinanceStatisticsWindow, FinanceStatisticsWindow]:
        today = now.astimezone(time_zone).date()
        granularity = FinanceStatisticsGranularity.DAY
        if period == FinanceStatisticsPeriod.TODAY:
            start = today
            end = today + timedelta(days=1)
            previous_start = start - timedelta(days=1)
            granularity = FinanceStatisticsGranularity.HOUR
        elif period == FinanceStatisticsPeriod.THIS_WEEK:
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=7)
            previous_start = start - timedelta(days=7)
        elif period == FinanceStatisticsPeriod.THIS_MONTH:
            start = today.replace(day=1)
            end = next_month(start)
            previous_start = (start - timedelta(days=1)).replace(day=1)
        elif period == FinanceStatisticsPeriod.THIS_YEAR:
            start = date(today.year, 1, 1)
            end = date(today.year + 1, 1, 1)
            previous_start = date(today.year - 1, 1, 1)
            granularity = FinanceStatisticsGranularity.MONTH
        else:
            days = {
                FinanceStatisticsPeriod.LAST_7_DAYS: 7,
                FinanceStatisticsPeriod.LAST_30_DAYS: 30,
                FinanceStatisticsPeriod.LAST_365_DAYS: 365,
            }[period]
            end = today + timedelta(days=1)
            start = end - timedelta(days=days)
            previous_start = start - timedelta(days=days)
            if period == FinanceStatisticsPeriod.LAST_365_DAYS:
                granularity = FinanceStatisticsGranularity.MONTH
        return (
            cls(
                start=datetime.combine(start, datetime.min.time(), time_zone),
                end=datetime.combine(end, datetime.min.time(), time_zone),
                granularity=granularity,
            ),
            cls(
                start=datetime.combine(previous_start, datetime.min.time(), time_zone),
                end=datetime.combine(start, datetime.min.time(), time_zone),
                granularity=granularity,
            ),
        )

    def contains(self, occurred_at: datetime) -> bool:
        return self.start <= occurred_at < self.end


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceStatisticsFact:
    currency: FinanceCurrency
    occurred_at: datetime
    kind: FinanceKind
    amount: Amount
    category_id: str
    category_name: str
    category_period: date


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceStatisticsSource:
    available_since: date
    facts: list[FinanceStatisticsFact]
    currencies: list[FinanceCurrency]


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceStatisticsPoint:
    start: datetime
    end: datetime
    amount: Amount


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceStatisticsCategory:
    id: str
    name: str
    amount: Amount
    percentage: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceStatisticsBreakdown:
    actual: Amount
    previous: Amount
    change: Amount
    change_percent: Decimal | None
    timeline: list[FinanceStatisticsPoint]
    categories: list[FinanceStatisticsCategory]


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceStatistics:
    budget_rate_effective_on: date | None
    period: FinanceStatisticsPeriod
    currency: FinanceCurrency
    timezone_name: str
    window: FinanceStatisticsWindow
    previous_window: FinanceStatisticsWindow
    available_since: date
    income: FinanceStatisticsBreakdown
    expense: FinanceStatisticsBreakdown
    net: Amount
    previous_net: Amount
    uncategorized_income: Amount
    uncategorized_expense: Amount
    monthly: FinanceMonth | None


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceTransactionMonthParams(FinanceMonthParams):
    period_start: date | None
    lock: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceStatisticsResult:
    currency: FinanceStatisticsCurrency
    reports: list[FinanceStatistics]


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceStatisticsComposition:
    params: FinanceStatisticsParams
    month: FinanceMonth
    window: FinanceStatisticsWindow
    previous_window: FinanceStatisticsWindow
    source: FinanceStatisticsSource
    budget_rate: FinanceRateSet | None
