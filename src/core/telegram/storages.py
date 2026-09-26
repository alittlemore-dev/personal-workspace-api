from abc import ABC, abstractmethod
from datetime import datetime

from core.telegram.enums import TelegramConnectionState
from core.telegram.schemas import (
    TelegramConnection,
    TelegramInvitation,
    TelegramParticipant,
)


class TelegramStorage(ABC):
    @abstractmethod
    async def count_recent_invitations(self, *, owner_username: str, since: datetime) -> int: ...

    @abstractmethod
    async def replace_invitation(
        self,
        *,
        owner_username: str,
        token_hash: str,
        label: str,
        expires_at: datetime,
        now: datetime,
    ) -> TelegramInvitation: ...

    @abstractmethod
    async def get_invitation(self, *, token_hash: str, lock: bool) -> TelegramInvitation | None: ...

    @abstractmethod
    async def consume_invitation(self, *, invitation_id: str, now: datetime) -> None: ...

    @abstractmethod
    async def cancel_invitation(
        self,
        *,
        owner_username: str,
        invitation_id: str,
        now: datetime,
    ) -> None: ...

    @abstractmethod
    async def list_invitations(
        self,
        *,
        owner_username: str,
        now: datetime,
    ) -> list[TelegramInvitation]: ...

    @abstractmethod
    async def list_connections(self, *, owner_username: str) -> list[TelegramConnection]: ...

    @abstractmethod
    async def count_live_connections(
        self,
        *,
        owner_username: str,
        pending_since: datetime,
    ) -> int: ...

    @abstractmethod
    async def get_connection(self, *, connection_id: str) -> TelegramConnection | None: ...

    @abstractmethod
    async def get_connection_for_user(
        self,
        *,
        owner_username: str,
        telegram_user_id: int,
    ) -> TelegramConnection | None: ...

    @abstractmethod
    async def has_active_connection(self, *, telegram_user_id: int) -> bool: ...

    @abstractmethod
    async def create_pending_connection(
        self,
        *,
        owner_username: str,
        participant: TelegramParticipant,
        label: str,
        now: datetime,
    ) -> TelegramConnection: ...

    @abstractmethod
    async def set_connection_state(
        self,
        *,
        connection_id: str,
        state: TelegramConnectionState,
        now: datetime,
    ) -> TelegramConnection: ...

    @abstractmethod
    async def set_connection_label(
        self,
        *,
        connection_id: str,
        label: str,
    ) -> TelegramConnection: ...


class TelegramRedemptionLimiter(ABC):
    @abstractmethod
    async def allow_attempt(self, *, telegram_user_id: int) -> bool: ...


class TelegramAccountSettingsReader(ABC):
    @abstractmethod
    async def is_enabled(self, *, owner_username: str) -> bool: ...


class TelegramTransaction(ABC):
    @abstractmethod
    async def commit(self) -> None: ...

    @abstractmethod
    async def rollback(self) -> None: ...
