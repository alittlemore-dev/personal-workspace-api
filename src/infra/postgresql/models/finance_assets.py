from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, Enum, ForeignKey, Index, String, UniqueConstraint, Uuid, false
from sqlalchemy.orm import Mapped, declared_attr, mapped_column
from sqlalchemy_dev_utils.types.datetime import UTCDateTime
from sqlalchemy_dev_utils.types.pydantic import PydanticType

from core.finance.assets.enums import AssetMovementKind, AssetPositionKind, AssetSource
from core.finance.enums import FinanceCurrency
from infra.postgresql.models.base import BaseModel, TableArgs
from infra.postgresql.models.finance import (
    CURRENCY,
    MONEY,
    FinanceMonthModel,
    FinanceRateSetModel,
    FinanceTrackerModel,
    FinanceTransactionModel,
)
from infra.postgresql.models.mixins.ids import HexUuidIDMixin
from infra.postgresql.schemas.finance_assets import AssetDraftSnapshot, AssetRevisionSnapshot


class AssetTrackerMixin:
    tracker_id: Mapped[str] = mapped_column(
        ForeignKey(FinanceTrackerModel.id, ondelete="CASCADE"),
        index=True,
    )


class AssetLocationModel(AssetTrackerMixin, HexUuidIDMixin, BaseModel):
    name: Mapped[str] = mapped_column(String(255))


class AssetPositionModel(AssetTrackerMixin, HexUuidIDMixin, BaseModel):
    __table_args__ = (
        UniqueConstraint(
            "tracker_id",
            "creation_request_id",
            name="asset_position_creation_request_uq",
        ),
    )
    archived: Mapped[bool] = mapped_column(server_default=false())
    creation_request_id: Mapped[UUID | None] = mapped_column(Uuid)
    creation_signature: Mapped[str | None] = mapped_column(String(64))
    location_id: Mapped[str] = mapped_column(ForeignKey(AssetLocationModel.id, ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[AssetPositionKind] = mapped_column(
        Enum(AssetPositionKind, name="asset_position_kind_enum"),
    )
    currency: Mapped[FinanceCurrency] = mapped_column(CURRENCY)
    instrument: Mapped[str] = mapped_column(String(255))
    venue: Mapped[str] = mapped_column(String(255))
    annual_rate: Mapped[Decimal | None] = mapped_column(MONEY)
    matures_on: Mapped[date | None] = mapped_column(Date)


class AssetMovementModel(AssetTrackerMixin, HexUuidIDMixin, BaseModel):
    request_id: Mapped[UUID] = mapped_column(Uuid)
    position_id: Mapped[str] = mapped_column(ForeignKey(AssetPositionModel.id))
    counter_position_id: Mapped[str | None] = mapped_column(ForeignKey(AssetPositionModel.id))
    on_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[AssetMovementKind] = mapped_column(
        Enum(AssetMovementKind, name="asset_movement_kind_enum"),
    )
    source: Mapped[AssetSource] = mapped_column(
        Enum(AssetSource, name="asset_movement_source_enum"),
    )
    draft: Mapped[AssetDraftSnapshot] = mapped_column(PydanticType(AssetDraftSnapshot))
    month_id: Mapped[str | None] = mapped_column(ForeignKey(FinanceMonthModel.id))
    rate_set_id: Mapped[str | None] = mapped_column(ForeignKey(FinanceRateSetModel.id))
    budget_amount_rub: Mapped[Decimal | None] = mapped_column(MONEY)
    transaction_id: Mapped[str | None] = mapped_column(
        ForeignKey(FinanceTransactionModel.id),
        unique=True,
    )
    version: Mapped[int] = mapped_column()
    deleted: Mapped[bool]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime)

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgs:
        return (
            UniqueConstraint(cls.tracker_id, cls.request_id),
            Index("asset_movement_tracker_date_idx", cls.tracker_id, cls.on_date),
            Index("asset_movement_month_idx", cls.month_id),
        )


class AssetMovementRevisionModel(HexUuidIDMixin, BaseModel):
    movement_id: Mapped[str] = mapped_column(ForeignKey(AssetMovementModel.id, ondelete="CASCADE"))
    version: Mapped[int] = mapped_column()
    snapshot: Mapped[AssetRevisionSnapshot] = mapped_column(PydanticType(AssetRevisionSnapshot))

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgs:
        return (UniqueConstraint(cls.movement_id, cls.version),)
