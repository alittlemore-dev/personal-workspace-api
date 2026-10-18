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
)
from core.i18n.enums import LanguageEnum
from entrypoints.litestar.api.schemas import CamelCaseSchema


class EnsureFinanceMonthRequest(CamelCaseSchema):
    language: LanguageEnum = Field(
        description="Language; allowed values are listed in the referenced enumeration.",
        examples=["en"],
    )


class OpeningBalanceRequest(CamelCaseSchema):
    amount: Decimal = Field(
        description=(
            "Monetary amount serialized as a decimal string; requests "
            "also accept JSON numbers. AMD uses whole units; RUB, USD, "
            "and EUR allow at most two decimal places. Values must be "
            "finite with magnitude below 10^18."
        ),
        examples=["1250.50"],
    )


class ChangeMonthCurrencyRequest(CamelCaseSchema):
    currency: FinanceCurrency = Field(
        description="Currency; allowed values are listed in the referenced enumeration.",
        examples=["RUB"],
    )


class CreateFinanceCategoryRequest(CamelCaseSchema):
    kind: FinanceKind = Field(
        description="Kind; allowed values are listed in the referenced enumeration.",
        examples=["expense"],
    )
    name: str = Field(
        max_length=255,
        description="User-defined finance category name.",
        examples=["Groceries"],
    )
    planned_amount: Decimal | None = Field(
        description="Planned category amount; null when no plan is set.",
        examples=["15000.00"],
    )


class UpdateFinanceCategoryRequest(CamelCaseSchema):
    name: str = Field(
        max_length=255,
        description="User-defined finance category name.",
        examples=["Groceries"],
    )
    planned_amount: Decimal | None = Field(
        description="Planned category amount; null when no plan is set.",
        examples=["15000.00"],
    )
    position: int = Field(description="Zero-based position in display order.", examples=[0])


class FinanceCategoryResponse(CamelCaseSchema):
    id: str = Field(
        description="Opaque resource identifier; use the value returned by this API.",
        examples=["4e92d4de561f4bc7a3eed227868952db"],
    )
    stable_id: str = Field(
        description=(
            "Stable category identity shared by its snapshots across months. "
            "Transaction requests use id, not stableId."
        ),
        examples=["1bb209e394954b71bd78b52d572dd835"],
    )
    kind: FinanceKind = Field(
        description="Kind; allowed values are listed in the referenced enumeration.",
        examples=["expense"],
    )
    name: str = Field(description="User-defined finance category name.", examples=["Groceries"])
    planned_amount: Decimal | None = Field(
        description="Planned category amount; null when no plan is set.",
        examples=["15000.00"],
    )
    actual_amount: Decimal = Field(
        description="Actual total recorded for this category.",
        examples=["1250.50"],
    )
    difference: Decimal | None = Field(
        description="Difference between the plan and actual amount; null when no plan is set.",
        examples=["13749.50"],
    )
    position: int = Field(description="Zero-based position in display order.", examples=[0])
    archived: bool = Field(description="Whether the category is archived.", examples=[False])


class FinanceMonthResponse(CamelCaseSchema):
    id: str = Field(
        description="Opaque resource identifier; use the value returned by this API.",
        examples=["4e92d4de561f4bc7a3eed227868952db"],
    )
    period_start: date = Field(
        description="First calendar day of the finance month in the account time zone.",
        examples=["2026-10-01"],
    )
    timezone_name: str = Field(
        description="IANA time zone used for calendar boundaries.",
        examples=["Asia/Yerevan"],
    )
    currency: FinanceCurrency = Field(
        description="Currency; allowed values are listed in the referenced enumeration.",
        examples=["RUB"],
    )
    opening_balance: Decimal = Field(
        description="Balance at the start of the month.",
        examples=["20000.00"],
    )
    actual_income: Decimal = Field(
        description="Recorded income in the month currency.",
        examples=["80000.00"],
    )
    actual_expense: Decimal = Field(
        description="Recorded expenses in the month currency.",
        examples=["1250.50"],
    )
    planned_income: Decimal | None = Field(
        description="Planned income; null when no income plan exists.",
        examples=["80000.00"],
    )
    planned_expense: Decimal | None = Field(
        description="Planned expenses; null when no expense plan exists.",
        examples=["40000.00"],
    )
    closing_balance: Decimal = Field(
        description="Opening balance plus actual income minus actual expense.",
        examples=["98749.50"],
    )
    categories: list[FinanceCategoryResponse] = Field(
        description="Categories returned by this operation.",
    )

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
    category_id: str = Field(
        description="Category snapshot id in this finance month (not the cross-month stableId).",
        examples=["4e92d4de561f4bc7a3eed227868952db"],
    )
    amount: Decimal = Field(
        description=(
            "Monetary amount serialized as a decimal string; requests "
            "also accept JSON numbers. AMD uses whole units; RUB, USD, "
            "and EUR allow at most two decimal places. Values must be "
            "finite with magnitude below 10^18."
        ),
        examples=["1250.50"],
    )
    currency: FinanceCurrency = Field(
        description="Currency; allowed values are listed in the referenced enumeration.",
        examples=["RUB"],
    )
    occurred_at: datetime = Field(
        description="Transaction timestamp including its UTC offset.",
        examples=["2026-10-18T09:00:00Z"],
    )
    description: str = Field(
        max_length=2000,
        description="Transaction note, up to 2000 characters.",
        examples=["Weekly groceries"],
    )

    def to_domain_schema(self) -> FinanceTransactionDraft:
        return FinanceTransactionDraft(
            category_id=self.category_id,
            amount=Amount(self.amount),
            currency=self.currency,
            occurred_at=self.occurred_at,
            description=self.description,
        )


class FinanceTransactionUpdateRequest(FinanceTransactionRequest):
    version: int = Field(
        description=(
            "Optimistic concurrency version. Send the latest returned version; "
            "stale versions produce HTTP 409."
        ),
        examples=[2],
    )


class FinanceVersionRequest(CamelCaseSchema):
    version: int = Field(
        description=(
            "Optimistic concurrency version. Send the latest returned version; "
            "stale versions produce HTTP 409."
        ),
        examples=[2],
    )


class FinanceTransactionResponse(CamelCaseSchema):
    created_at: datetime = Field(
        description="Creation timestamp in ISO 8601 format.",
        examples=["2026-10-18T09:00:00Z"],
    )
    source: FinanceSource = Field(
        description="Transaction source: web or telegram.",
        examples=["web"],
    )
    author_id: str = Field(
        description="Username of the transaction author.",
        examples=["alex.morgan"],
    )
    author_label: str = Field(
        description="Display label for the transaction author.",
        examples=["Alex Morgan"],
    )
    id: str = Field(
        description="Opaque resource identifier; use the value returned by this API.",
        examples=["4e92d4de561f4bc7a3eed227868952db"],
    )
    category_id: str | None = Field(
        description="Category snapshot id in this finance month (not the cross-month stableId).",
        examples=["4e92d4de561f4bc7a3eed227868952db"],
    )
    category_name: str = Field(
        description="Category name recorded for this transaction.",
        examples=["Groceries"],
    )
    kind: FinanceKind = Field(
        description="Kind; allowed values are listed in the referenced enumeration.",
        examples=["expense"],
    )
    amount: Decimal = Field(
        description=(
            "Monetary amount serialized as a decimal string; requests "
            "also accept JSON numbers. AMD uses whole units; RUB, USD, "
            "and EUR allow at most two decimal places. Values must be "
            "finite with magnitude below 10^18."
        ),
        examples=["1250.50"],
    )
    currency: FinanceCurrency = Field(
        description="Currency; allowed values are listed in the referenced enumeration.",
        examples=["RUB"],
    )
    converted_amount: Decimal = Field(
        description="Transaction amount converted to the finance month currency.",
        examples=["1250.50"],
    )
    occurred_at: datetime = Field(
        description="Transaction timestamp including its UTC offset.",
        examples=["2026-10-18T09:00:00Z"],
    )
    description: str = Field(
        description="Transaction note, up to 2000 characters.",
        examples=["Weekly groceries"],
    )
    rate_effective_on: date = Field(
        description="Effective date of the currency conversion rate.",
        examples=["2026-10-18"],
    )
    version: int = Field(
        description=(
            "Optimistic concurrency version. Send the latest returned version; "
            "stale versions produce HTTP 409."
        ),
        examples=[2],
    )
    deleted: bool = Field(description="Whether this transaction is soft deleted.", examples=[False])

    @classmethod
    def from_domain(cls, transaction: FinanceTransaction) -> FinanceTransactionResponse:
        return cls.model_validate(transaction)


class FinanceTransactionsResponse(CamelCaseSchema):
    transactions: list[FinanceTransactionResponse] = Field(
        description="Transactions returned by this operation.",
    )

    @classmethod
    def from_domain(cls, transactions: FinanceTransactions) -> FinanceTransactionsResponse:
        return cls.model_validate(transactions)


class FinanceTransactionSnapshotSchema(CamelCaseSchema):
    category_id: str | None = Field(
        description=("Month category snapshot identifier; null after permanent category deletion."),
        examples=["4e92d4de561f4bc7a3eed227868952db"],
    )
    kind: str = Field(
        description="Recorded transaction kind: income or expense.",
        examples=["expense"],
    )
    amount: str = Field(
        description="Original transaction amount as a decimal string.",
        examples=["1250.50"],
    )
    currency: str = Field(description="Original transaction currency.", examples=["RUB"])
    amount_rub: str = Field(
        description="Transaction value in RUB recorded for conversion.",
        examples=["1250.50"],
    )
    rate_set_id: str = Field(
        description="Identifier of the stored exchange-rate set.",
        examples=["cabe3a7dd502458aa35e3d95d0953eaf"],
    )
    occurred_at: str = Field(
        description="Original occurrence timestamp including UTC offset.",
        examples=["2026-10-18T09:00:00Z"],
    )
    description: str = Field(
        description="Transaction note before this revision.",
        examples=["Weekly groceries"],
    )
    version: int = Field(description="Transaction version before this revision.", examples=[1])
    deleted: bool = Field(description="Deletion state before this revision.", examples=[False])


class FinanceRevisionResponse(CamelCaseSchema):
    number: int = Field(description="Sequential revision number.", examples=[2])
    action: FinanceRevisionAction = Field(
        description="Action; allowed values are listed in the referenced enumeration.",
        examples=["update"],
    )
    previous_state: FinanceTransactionSnapshotSchema = Field(
        description="Previous state; see the nested schema for its fields.",
    )
    actor_username: str = Field(
        description="Username that performed this revision.",
        examples=["alex.morgan"],
    )
    changed_at: datetime = Field(
        description="Revision timestamp in ISO 8601 format.",
        examples=["2026-10-18T10:30:00Z"],
    )

    @classmethod
    def from_domain(cls, revision: FinanceTransactionRevision) -> FinanceRevisionResponse:
        return cls.model_validate(revision)


class FinanceRevisionsResponse(CamelCaseSchema):
    revisions: list[FinanceRevisionResponse] = Field(
        description="Revisions returned by this operation.",
    )

    @classmethod
    def from_domain(cls, revisions: FinanceRevisions) -> FinanceRevisionsResponse:
        return cls.model_validate(revisions)


class FinanceStatisticsWindowResponse(CamelCaseSchema):
    start: datetime = Field(
        description="Inclusive interval start.",
        examples=["2026-10-18T09:00:00Z"],
    )
    end: datetime = Field(
        description="Exclusive interval end; must follow start.",
        examples=["2026-10-18T10:00:00Z"],
    )
    granularity: FinanceStatisticsGranularity = Field(
        description="Granularity; allowed values are listed in the referenced enumeration.",
        examples=["day"],
    )


class FinanceStatisticsPointResponse(CamelCaseSchema):
    start: datetime = Field(
        description="Inclusive interval start.",
        examples=["2026-10-18T09:00:00Z"],
    )
    end: datetime = Field(
        description="Exclusive interval end; must follow start.",
        examples=["2026-10-18T10:00:00Z"],
    )
    amount: Decimal = Field(
        description=(
            "Monetary amount serialized as a decimal string; requests "
            "also accept JSON numbers. AMD uses whole units; RUB, USD, "
            "and EUR allow at most two decimal places. Values must be "
            "finite with magnitude below 10^18."
        ),
        examples=["1250.50"],
    )


class FinanceStatisticsCategoryResponse(CamelCaseSchema):
    id: str = Field(
        description="Opaque resource identifier; use the value returned by this API.",
        examples=["4e92d4de561f4bc7a3eed227868952db"],
    )
    name: str = Field(description="User-defined finance category name.", examples=["Groceries"])
    amount: Decimal = Field(
        description=(
            "Monetary amount serialized as a decimal string; requests "
            "also accept JSON numbers. AMD uses whole units; RUB, USD, "
            "and EUR allow at most two decimal places. Values must be "
            "finite with magnitude below 10^18."
        ),
        examples=["1250.50"],
    )
    percentage: Decimal = Field(
        description="Share of the total as a percentage.",
        examples=["35.50"],
    )


class FinanceStatisticsBreakdownResponse(CamelCaseSchema):
    actual: Decimal = Field(
        description="Total amount in the selected reporting window.",
        examples=["1250.50"],
    )
    previous: Decimal = Field(
        description="Total amount in the comparison window.",
        examples=["1000.00"],
    )
    change: Decimal = Field(
        description="Current total minus the comparison total.",
        examples=["250.50"],
    )
    change_percent: Decimal | None = Field(
        description="Percentage change; null when the comparison total is zero.",
        examples=["25.05"],
    )
    timeline: list[FinanceStatisticsPointResponse] = Field(
        description="Timeline returned by this operation.",
    )
    categories: list[FinanceStatisticsCategoryResponse] = Field(
        description="Categories returned by this operation.",
    )


class FinanceStatisticsResponse(CamelCaseSchema):
    budget_rate_effective_on: date | None = Field(
        description=(
            "Effective conversion-rate date for the month budget; null when no budget rate applies."
        ),
        examples=["2026-10-01"],
    )
    period: FinanceStatisticsPeriod = Field(
        description="Period; allowed values are listed in the referenced enumeration.",
        examples=["thisMonth"],
    )
    currency: FinanceCurrency = Field(
        description="Currency; allowed values are listed in the referenced enumeration.",
        examples=["RUB"],
    )
    timezone_name: str = Field(
        description="IANA time zone used for calendar boundaries.",
        examples=["Asia/Yerevan"],
    )
    window: FinanceStatisticsWindowResponse = Field(
        description="Window; see the nested schema for its fields.",
    )
    previous_window: FinanceStatisticsWindowResponse = Field(
        description="Previous window; see the nested schema for its fields.",
    )
    available_since: date = Field(
        description="Earliest date covered by the finance history.",
        examples=["2026-01-01"],
    )
    income: FinanceStatisticsBreakdownResponse = Field(
        description="Income; see the nested schema for its fields.",
    )
    expense: FinanceStatisticsBreakdownResponse = Field(
        description="Expense; see the nested schema for its fields.",
    )
    net: Decimal = Field(
        description="Income minus expenses for the selected window.",
        examples=["78749.50"],
    )
    previous_net: Decimal = Field(
        description="Income minus expenses in the comparison window.",
        examples=["70000.00"],
    )
    uncategorized_income: Decimal = Field(
        description="Income without a current category.",
        examples=["0.00"],
    )
    uncategorized_expense: Decimal = Field(
        description="Expenses without a current category.",
        examples=["0.00"],
    )
    monthly: FinanceMonthResponse | None = Field(
        description="Monthly; see the nested schema for its fields.",
    )

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
    currency: FinanceStatisticsCurrency = Field(
        description="Currency; allowed values are listed in the referenced enumeration.",
        examples=["RUB"],
    )
    reports: list[FinanceStatisticsResponse] = Field(
        description="Reports returned by this operation.",
    )

    @classmethod
    def from_domain(cls, result: FinanceStatisticsResult) -> FinanceStatisticsResultResponse:
        return cls(
            currency=result.currency,
            reports=[FinanceStatisticsResponse.from_domain(report) for report in result.reports],
        )
