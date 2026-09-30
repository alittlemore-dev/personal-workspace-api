from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from core.finance.schemas import FinanceTransactionSnapshot


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
