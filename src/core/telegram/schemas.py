from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256

from core.telegram.enums import TelegramConnectionState
from core.telegram.exceptions import TelegramAccessError, TelegramInvitationError


class InvitationToken(str):
    __slots__ = ()

    @property
    def hash(self) -> str:
        return sha256(self.encode()).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class TelegramUseCaseConfig:
    bot_username: str
    invitation_limit: int
    connection_limit: int
    available: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class TelegramInvitation:
    id: str
    owner_username: str
    token_hash: str
    label: str
    expires_at: datetime
    used_at: datetime | None
    cancelled_at: datetime | None

    def require_usable(self, *, now: datetime) -> None:
        if self.used_at is not None or self.cancelled_at is not None or self.expires_at <= now:
            raise TelegramInvitationError


@dataclass(frozen=True, slots=True, kw_only=True)
class IssuedTelegramInvitation:
    token: InvitationToken = field(repr=False)
    bot_username: str
    expires_at: datetime

    @property
    def url(self) -> str:
        return f"https://t.me/{self.bot_username}?start={self.token}"

    @property
    def token_hash(self) -> str:
        return self.token.hash


@dataclass(frozen=True, slots=True, kw_only=True)
class TelegramParticipant:
    user_id: int
    private_chat_id: int
    first_name: str
    username: str


@dataclass(frozen=True, slots=True, kw_only=True)
class TelegramConnection:
    id: str
    owner_username: str
    telegram_user_id: int
    private_chat_id: int
    label: str
    first_name: str
    username: str
    state: TelegramConnectionState
    requested_at: datetime
    connected_at: datetime | None
    last_contact_at: datetime

    def require_owner(self, *, owner_username: str) -> None:
        if self.owner_username != owner_username:
            raise TelegramAccessError
