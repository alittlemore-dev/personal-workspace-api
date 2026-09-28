from datetime import date, datetime

from sqlalchemy import Date, Enum, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, declared_attr, mapped_column
from sqlalchemy_dev_utils.types.datetime import UTCDateTime

from core.notifications.enums import DeliveryStatus, ReminderKind
from infra.postgresql.models.base import BaseModel, TableArgs
from infra.postgresql.models.mixins.ids import HexUuidIDMixin


class ReminderDeliveryModel(HexUuidIDMixin, BaseModel):
    connection_id: Mapped[str] = mapped_column(String(32))
    kind: Mapped[ReminderKind] = mapped_column(
        Enum(ReminderKind, name="reminder_kind_enum", native_enum=True),
    )
    item_id: Mapped[str] = mapped_column(String(32))
    occurrence_date: Mapped[date] = mapped_column(Date)
    lead_days: Mapped[int] = mapped_column(Integer)
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus, name="reminder_delivery_status_enum", native_enum=True),
    )
    attempts: Mapped[int] = mapped_column(Integer)
    claimed_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(UTCDateTime)
    next_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgs:
        return (
            UniqueConstraint(
                cls.connection_id,
                cls.kind,
                cls.item_id,
                cls.occurrence_date,
                cls.lead_days,
                name="reminder_delivery_once_uniq",
            ),
            Index("reminder_delivery_status_retry_idx", cls.status, cls.next_attempt_at),
        )
