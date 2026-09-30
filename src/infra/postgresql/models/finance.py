from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column
from sqlalchemy_dev_utils.types.datetime import UTCDateTime
from sqlalchemy_dev_utils.types.pydantic import PydanticType

from core.finance.enums import FinanceCurrency, FinanceKind, FinanceRevisionAction
from infra.postgresql.models.base import BaseModel, TableArgs
from infra.postgresql.models.mixins.ids import HexUuidIDMixin
from infra.postgresql.schemas.finance import (
    FinanceMonthCurrencySnapshotSchema,
    FinanceTransactionSnapshotSchema,
)
from infra.postgresql.types import ZoneInfoType

MONEY = Numeric(30, 12)
RATE = Numeric(30, 18)
CURRENCY = Enum(FinanceCurrency, name="finance_currency_enum", native_enum=True)
KIND = Enum(FinanceKind, name="finance_kind_enum", native_enum=True)
ACTION = Enum(FinanceRevisionAction, name="finance_revision_action_enum", native_enum=True)


class FinanceTemplateCategoryModel(HexUuidIDMixin, BaseModel):
    key: Mapped[str] = mapped_column(String(80), unique=True)
    kind: Mapped[FinanceKind] = mapped_column(KIND)
    name_ru: Mapped[str] = mapped_column(String(255))
    name_en: Mapped[str] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer)


class FinanceTrackerModel(HexUuidIDMixin, BaseModel):
    owner_username: Mapped[str] = mapped_column(String(255), unique=True)
    time_zone: Mapped[ZoneInfo] = mapped_column("timezone_name", ZoneInfoType())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class FinanceMonthModel(HexUuidIDMixin, BaseModel):
    tracker_id: Mapped[str] = mapped_column(ForeignKey(FinanceTrackerModel.id, ondelete="CASCADE"))
    period_start: Mapped[date] = mapped_column(Date)
    currency: Mapped[FinanceCurrency] = mapped_column(CURRENCY)
    opening_balance: Mapped[Decimal] = mapped_column(MONEY)
    previous_month_id: Mapped[str | None] = mapped_column(
        ForeignKey("finance__finance_month_model.id"),
    )
    transferred_balance: Mapped[Decimal | None] = mapped_column(MONEY)
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgs:
        return (UniqueConstraint(cls.tracker_id, cls.period_start),)


class FinanceCategoryModel(HexUuidIDMixin, BaseModel):
    tracker_id: Mapped[str] = mapped_column(ForeignKey(FinanceTrackerModel.id, ondelete="CASCADE"))
    kind: Mapped[FinanceKind] = mapped_column(KIND)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class FinanceMonthCategoryModel(HexUuidIDMixin, BaseModel):
    month_id: Mapped[str] = mapped_column(ForeignKey(FinanceMonthModel.id, ondelete="CASCADE"))
    category_id: Mapped[str] = mapped_column(
        ForeignKey(FinanceCategoryModel.id, ondelete="CASCADE"),
    )
    kind: Mapped[FinanceKind] = mapped_column(KIND)
    name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255))
    planned_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    position: Mapped[int] = mapped_column(Integer)
    accepting_transactions: Mapped[bool] = mapped_column(Boolean)
    source_month_category_id: Mapped[str | None] = mapped_column(
        ForeignKey("finance__finance_month_category_model.id", ondelete="SET NULL"),
    )

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgs:
        return (
            UniqueConstraint(cls.month_id, cls.category_id),
            UniqueConstraint(cls.month_id, cls.kind, cls.normalized_name),
            Index("finance_month_category_order_idx", cls.month_id, cls.kind, cls.position),
        )


class FinanceRateSetModel(HexUuidIDMixin, BaseModel):
    provider: Mapped[str] = mapped_column(String(50))
    effective_on: Mapped[date] = mapped_column(Date)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime)
    payload_hash: Mapped[str] = mapped_column(String(64))

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgs:
        return (UniqueConstraint(cls.provider, cls.effective_on, cls.payload_hash),)


class FinanceRateModel(BaseModel):
    rate_set_id: Mapped[str] = mapped_column(
        ForeignKey(FinanceRateSetModel.id, ondelete="CASCADE"),
        primary_key=True,
    )
    currency: Mapped[FinanceCurrency] = mapped_column(CURRENCY, primary_key=True)
    nominal: Mapped[int] = mapped_column(Integer)
    rub_per_unit: Mapped[Decimal] = mapped_column(RATE)


class FinanceTransactionModel(HexUuidIDMixin, BaseModel):
    month_id: Mapped[str] = mapped_column(ForeignKey(FinanceMonthModel.id))
    month_category_id: Mapped[str | None] = mapped_column(
        ForeignKey(FinanceMonthCategoryModel.id, ondelete="SET NULL"),
    )
    kind: Mapped[FinanceKind] = mapped_column(KIND)
    original_amount: Mapped[Decimal] = mapped_column(MONEY)
    original_currency: Mapped[FinanceCurrency] = mapped_column(CURRENCY)
    amount_rub: Mapped[Decimal] = mapped_column(MONEY)
    rate_set_id: Mapped[str] = mapped_column(ForeignKey(FinanceRateSetModel.id))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime)
    description: Mapped[str] = mapped_column(String(2000))
    author_username: Mapped[str] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgs:
        return (Index("finance_transaction_month_date_idx", cls.month_id, cls.occurred_at),)


class FinanceTransactionRevisionModel(HexUuidIDMixin, BaseModel):
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey(FinanceTransactionModel.id, ondelete="CASCADE"),
    )
    number: Mapped[int] = mapped_column(Integer)
    action: Mapped[FinanceRevisionAction] = mapped_column(ACTION)
    previous_state: Mapped[FinanceTransactionSnapshotSchema] = mapped_column(
        PydanticType(FinanceTransactionSnapshotSchema),
    )
    actor_username: Mapped[str] = mapped_column(String(255))
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime)

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgs:
        return (UniqueConstraint(cls.transaction_id, cls.number),)


class FinanceMonthCurrencyChangeModel(HexUuidIDMixin, BaseModel):
    month_id: Mapped[str] = mapped_column(ForeignKey(FinanceMonthModel.id))
    previous_currency: Mapped[FinanceCurrency] = mapped_column(CURRENCY)
    new_currency: Mapped[FinanceCurrency] = mapped_column(CURRENCY)
    rate_set_id: Mapped[str] = mapped_column(ForeignKey(FinanceRateSetModel.id))
    before_state: Mapped[FinanceMonthCurrencySnapshotSchema] = mapped_column(
        PydanticType(FinanceMonthCurrencySnapshotSchema),
    )
    after_state: Mapped[FinanceMonthCurrencySnapshotSchema] = mapped_column(
        PydanticType(FinanceMonthCurrencySnapshotSchema),
    )
    actor_username: Mapped[str] = mapped_column(String(255))
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime)
