from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from core.finance.enums import FinanceCurrency, FinanceKind, FinanceRevisionAction, FinanceSource
from core.finance.schemas import (
    Amount,
    FinanceMonth,
    FinanceRevisions,
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
