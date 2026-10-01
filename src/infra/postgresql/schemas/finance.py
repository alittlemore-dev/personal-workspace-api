from datetime import date
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from core.finance.enums import FinanceCurrency, FinanceKind, FinanceLimitScope
from core.finance.schemas import Amount, FinanceEventPayload, FinanceTransactionSnapshot


class FinanceTransactionSnapshotSchema(BaseModel):
    model_config = ConfigDict(frozen=True, serialize_by_alias=True, validate_by_name=True)

    category_id: str | None = Field(alias="categoryId")
    kind: str
    amount: str
    currency: str
    amount_rub: str = Field(alias="amountRub")
    rate_set_id: str = Field(alias="rateSetId")
    occurred_at: str = Field(alias="occurredAt")
    description: str
    version: int
    deleted: bool

    @classmethod
    def from_domain_schema(cls, snapshot: FinanceTransactionSnapshot) -> Self:
        return cls(
            category_id=snapshot["categoryId"],
            kind=snapshot["kind"],
            amount=snapshot["amount"],
            currency=snapshot["currency"],
            amount_rub=snapshot["amountRub"],
            rate_set_id=snapshot["rateSetId"],
            occurred_at=snapshot["occurredAt"],
            description=snapshot["description"],
            version=snapshot["version"],
            deleted=snapshot["deleted"],
        )

    def to_domain_schema(self) -> FinanceTransactionSnapshot:
        return {
            "categoryId": self.category_id,
            "kind": self.kind,
            "amount": self.amount,
            "currency": self.currency,
            "amountRub": self.amount_rub,
            "rateSetId": self.rate_set_id,
            "occurredAt": self.occurred_at,
            "description": self.description,
            "version": self.version,
            "deleted": self.deleted,
        }


class FinanceMonthCurrencySnapshotSchema(BaseModel):
    model_config = ConfigDict(frozen=True, serialize_by_alias=True, validate_by_name=True)

    opening_balance: str = Field(alias="openingBalance")
    plans: dict[str, str]


class FinanceEventPayloadSchema(BaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)
    month_id: str
    period_start: date
    transaction_id: str
    transaction_version: int
    author_id: str
    author_label: str
    source: str
    kind: FinanceKind
    amount: Decimal
    currency: FinanceCurrency
    category_id: str | None
    category_name: str
    limit_scope: FinanceLimitScope
    planned_amount: Decimal | None
    actual_amount: Decimal | None

    def to_domain_schema(self) -> FinanceEventPayload:
        return FinanceEventPayload(
            month_id=self.month_id,
            period_start=self.period_start,
            transaction_id=self.transaction_id,
            transaction_version=self.transaction_version,
            author_id=self.author_id,
            author_label=self.author_label,
            source=self.source,
            kind=self.kind,
            amount=Amount(self.amount),
            currency=self.currency,
            category_id=self.category_id,
            category_name=self.category_name,
            limit_scope=self.limit_scope,
            planned_amount=Amount(self.planned_amount) if self.planned_amount is not None else None,
            actual_amount=Amount(self.actual_amount) if self.actual_amount is not None else None,
        )
