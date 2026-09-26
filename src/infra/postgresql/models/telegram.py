from datetime import datetime

from sqlalchemy import BigInteger, Enum, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy_dev_utils.types.datetime import UTCDateTime

from core.telegram.enums import TelegramConnectionState
from core.telegram.schemas import TelegramConnection, TelegramInvitation
from infra.postgresql.models.base import BaseModel
from infra.postgresql.models.mixins.ids import HexUuidIDMixin


class TelegramInvitationModel(HexUuidIDMixin, BaseModel):
    owner_username: Mapped[str] = mapped_column(String(255), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    label: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    def to_domain_schema(self) -> TelegramInvitation:
        return TelegramInvitation(
            id=self.id,
            owner_username=self.owner_username,
            token_hash=self.token_hash,
            label=self.label,
            expires_at=self.expires_at,
            used_at=self.used_at,
            cancelled_at=self.cancelled_at,
        )


class TelegramConnectionModel(HexUuidIDMixin, BaseModel):
    owner_username: Mapped[str] = mapped_column(String(255), index=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger)
    private_chat_id: Mapped[int] = mapped_column(BigInteger)
    label: Mapped[str] = mapped_column(String(100))
    first_name: Mapped[str] = mapped_column(String(255))
    username: Mapped[str] = mapped_column(String(255))
    state: Mapped[TelegramConnectionState] = mapped_column(
        Enum(TelegramConnectionState, name="telegram_connection_state_enum", native_enum=True),
    )
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime)
    connected_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    state_changed_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_contact_at: Mapped[datetime] = mapped_column(UTCDateTime)

    __table_args__ = (
        Index(
            "telegram_connection_active_user_uidx",
            telegram_user_id,
            unique=True,
            postgresql_where=state == TelegramConnectionState.ACTIVE,
        ),
        Index(
            "telegram_connection_live_owner_user_uidx",
            owner_username,
            telegram_user_id,
            unique=True,
            postgresql_where=state.in_(
                (
                    TelegramConnectionState.PENDING,
                    TelegramConnectionState.ACTIVE,
                    TelegramConnectionState.BLOCKED,
                ),
            ),
        ),
    )

    def to_domain_schema(self) -> TelegramConnection:
        return TelegramConnection(
            id=self.id,
            owner_username=self.owner_username,
            telegram_user_id=self.telegram_user_id,
            private_chat_id=self.private_chat_id,
            label=self.label,
            first_name=self.first_name,
            username=self.username,
            state=self.state,
            requested_at=self.requested_at,
            connected_at=self.connected_at,
            last_contact_at=self.last_contact_at,
        )
