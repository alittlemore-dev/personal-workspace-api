from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, declared_attr, mapped_column
from sqlalchemy_dev_utils.types.datetime import UTCDateTime
from sqlalchemy_dev_utils.types.pydantic import PydanticType

from core.finance.enums import FinanceEventKind
from core.notifications.enums import DeliveryStatus
from infra.postgresql.models.base import BaseModel, TableArgs
from infra.postgresql.models.mixins.ids import HexUuidIDMixin
from infra.postgresql.schemas.finance import FinanceEventPayloadSchema


class FinanceEventModel(HexUuidIDMixin, BaseModel):
    owner_username: Mapped[str] = mapped_column(String(255), index=True)
    kind: Mapped[FinanceEventKind] = mapped_column(
        Enum(FinanceEventKind, name="finance_event_kind_enum", native_enum=True),
    )
    payload: Mapped[FinanceEventPayloadSchema] = mapped_column(
        PydanticType(FinanceEventPayloadSchema),
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    planned_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class FinanceDeliveryModel(HexUuidIDMixin, BaseModel):
    event_id: Mapped[str] = mapped_column(ForeignKey(FinanceEventModel.id, ondelete="CASCADE"))
    connection_id: Mapped[str] = mapped_column(String(32))
    kind: Mapped[FinanceEventKind] = mapped_column(
        Enum(FinanceEventKind, name="finance_event_kind_enum", native_enum=True),
    )
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus, name="reminder_delivery_status_enum", native_enum=True),
    )
    attempts: Mapped[int] = mapped_column(Integer)
    claimed_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    next_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgs:
        return (
            UniqueConstraint(
                cls.event_id,
                cls.connection_id,
                cls.kind,
                name="finance_delivery_once",
            ),
            Index("finance_delivery_due_idx", cls.status, cls.next_attempt_at),
        )
