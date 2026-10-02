from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from core.finance.enums import (
    FinanceCurrency,
    FinanceKind,
    FinanceRevisionAction,
    FinanceSource,
    FinanceStatisticsCurrency,
    FinanceStatisticsGranularity,
    FinanceStatisticsPeriod,
)
from core.finance.schemas import (
    Amount,
    FinanceMonth,
    FinanceRevisions,
    FinanceStatistics,
    FinanceStatisticsResult,
    FinanceTransaction,
    FinanceTransactionDraft,
    FinanceTransactionRevision,
    FinanceTransactions,
    FinanceTransactionSnapshot,
)
from core.i18n.enums import LanguageEnum
from entrypoints.litestar.api.schemas import CamelCaseSchema


class EnsureFinanceMonthRequest(CamelCaseSchema):
    language: LanguageEnum


class OpeningBalanceRequest(CamelCaseSchema):
    amount: Decimal


class ChangeMonthCurrencyRequest(CamelCaseSchema):
    currency: FinanceCurrency


class CreateFinanceCategoryRequest(CamelCaseSchema):
    kind: FinanceKind
    name: str = Field(max_length=255)
    planned_amount: Decimal | None


class UpdateFinanceCategoryRequest(CamelCaseSchema):
    name: str = Field(max_length=255)
    planned_amount: Decimal | None
    position: int


class FinanceCategoryResponse(CamelCaseSchema):
    id: str
    stable_id: str
    kind: FinanceKind
    name: str
    planned_amount: Decimal | None
    actual_amount: Decimal
    difference: Decimal | None
    position: int
    archived: bool


class FinanceMonthResponse(CamelCaseSchema):
    id: str
    period_start: date
    timezone_name: str
    currency: FinanceCurrency
    opening_balance: Decimal
    actual_income: Decimal
    actual_expense: Decimal
    planned_income: Decimal | None
    planned_expense: Decimal | None
    closing_balance: Decimal
    categories: list[FinanceCategoryResponse]

    @classmethod
    def from_domain(cls, month: FinanceMonth) -> FinanceMonthResponse:
        return cls(
            id=month.id,
            period_start=month.period_start,
            timezone_name=month.time_zone.key,
            currency=month.currency,
            opening_balance=month.opening_balance,
            actual_income=month.actual_income,
            actual_expense=month.actual_expense,
            planned_income=month.planned_income,
            planned_expense=month.planned_expense,
            closing_balance=month.closing_balance,
            categories=[FinanceCategoryResponse.model_validate(row) for row in month.categories],
        )


class FinanceTransactionRequest(CamelCaseSchema):
    category_id: str
    amount: Decimal
    currency: FinanceCurrency
    occurred_at: datetime
    description: str = Field(max_length=2000)

    def to_domain_schema(self) -> FinanceTransactionDraft:
        return FinanceTransactionDraft(
            category_id=self.category_id,
            amount=Amount(self.amount),
            currency=self.currency,
            occurred_at=self.occurred_at,
            description=self.description,
        )


class FinanceTransactionUpdateRequest(FinanceTransactionRequest):
    version: int


class FinanceVersionRequest(CamelCaseSchema):
    version: int


class FinanceTransactionResponse(CamelCaseSchema):
    created_at: datetime
    source: FinanceSource
    author_id: str
    author_label: str
    id: str
    category_id: str | None
    category_name: str
    kind: FinanceKind
    amount: Decimal
    currency: FinanceCurrency
    converted_amount: Decimal
    occurred_at: datetime
    description: str
    rate_effective_on: date
    version: int
    deleted: bool

    @classmethod
    def from_domain(cls, transaction: FinanceTransaction) -> FinanceTransactionResponse:
        return cls.model_validate(transaction)


class FinanceTransactionsResponse(CamelCaseSchema):
    transactions: list[FinanceTransactionResponse]

    @classmethod
    def from_domain(cls, transactions: FinanceTransactions) -> FinanceTransactionsResponse:
        return cls.model_validate(transactions)


class FinanceRevisionResponse(CamelCaseSchema):
    number: int
    action: FinanceRevisionAction
    previous_state: FinanceTransactionSnapshot
    actor_username: str
    changed_at: datetime

    @classmethod
    def from_domain(cls, revision: FinanceTransactionRevision) -> FinanceRevisionResponse:
        return cls.model_validate(revision)


class FinanceRevisionsResponse(CamelCaseSchema):
    revisions: list[FinanceRevisionResponse]

    @classmethod
    def from_domain(cls, revisions: FinanceRevisions) -> FinanceRevisionsResponse:
        return cls.model_validate(revisions)


class FinanceStatisticsWindowResponse(CamelCaseSchema):
    start: datetime
    end: datetime
    granularity: FinanceStatisticsGranularity


class FinanceStatisticsPointResponse(CamelCaseSchema):
    start: datetime
    end: datetime
    amount: Decimal


class FinanceStatisticsCategoryResponse(CamelCaseSchema):
    id: str
    name: str
    amount: Decimal
    percentage: Decimal


class FinanceStatisticsBreakdownResponse(CamelCaseSchema):
    actual: Decimal
    previous: Decimal
    change: Decimal
    change_percent: Decimal | None
    timeline: list[FinanceStatisticsPointResponse]
    categories: list[FinanceStatisticsCategoryResponse]


class FinanceStatisticsResponse(CamelCaseSchema):
    budget_rate_effective_on: date | None
    period: FinanceStatisticsPeriod
    currency: FinanceCurrency
    timezone_name: str
    window: FinanceStatisticsWindowResponse
    previous_window: FinanceStatisticsWindowResponse
    available_since: date
    income: FinanceStatisticsBreakdownResponse
    expense: FinanceStatisticsBreakdownResponse
    net: Decimal
    previous_net: Decimal
    uncategorized_income: Decimal
    uncategorized_expense: Decimal
    monthly: FinanceMonthResponse | None

    @classmethod
    def from_domain(cls, statistics: FinanceStatistics) -> FinanceStatisticsResponse:
        return cls(
            budget_rate_effective_on=statistics.budget_rate_effective_on,
            period=statistics.period,
            currency=statistics.currency,
            timezone_name=statistics.timezone_name,
            window=FinanceStatisticsWindowResponse.model_validate(statistics.window),
            previous_window=FinanceStatisticsWindowResponse.model_validate(
                statistics.previous_window,
            ),
            available_since=statistics.available_since,
            income=FinanceStatisticsBreakdownResponse.model_validate(statistics.income),
            expense=FinanceStatisticsBreakdownResponse.model_validate(statistics.expense),
            net=statistics.net,
            previous_net=statistics.previous_net,
            uncategorized_income=statistics.uncategorized_income,
            uncategorized_expense=statistics.uncategorized_expense,
            monthly=FinanceMonthResponse.from_domain(statistics.monthly)
            if statistics.monthly is not None
            else None,
        )


class FinanceStatisticsResultResponse(CamelCaseSchema):
    currency: FinanceStatisticsCurrency
    reports: list[FinanceStatisticsResponse]

    @classmethod
    def from_domain(cls, result: FinanceStatisticsResult) -> FinanceStatisticsResultResponse:
        return cls(
            currency=result.currency,
            reports=[FinanceStatisticsResponse.from_domain(report) for report in result.reports],
        )
