from dataclasses import dataclass
from datetime import datetime, timedelta

from core.telegram.enums import TelegramConnectionState
from core.telegram.exceptions import (
    TelegramAccessError,
    TelegramInvitationError,
    TelegramLimitError,
)
from core.telegram.generators import InvitationTokenGenerator
from core.telegram.schemas import (
    InvitationToken,
    IssuedTelegramInvitation,
    TelegramConnection,
    TelegramInvitation,
    TelegramParticipant,
    TelegramUseCaseConfig,
)
from core.telegram.storages import (
    TelegramAccountSettingsReader,
    TelegramRedemptionLimiter,
    TelegramStorage,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class TelegramUseCase:
    storage: TelegramStorage
    settings_reader: TelegramAccountSettingsReader
    token_generator: InvitationTokenGenerator
    config: TelegramUseCaseConfig
    limiter: TelegramRedemptionLimiter | None

    async def create_invitation(
        self,
        *,
        owner_username: str,
        label: str,
        now: datetime,
    ) -> IssuedTelegramInvitation:
        if not self.config.available or not await self.settings_reader.is_enabled(
            owner_username=owner_username,
        ):
            raise TelegramAccessError
        count = await self.storage.count_recent_invitations(
            owner_username=owner_username,
            since=now - timedelta(hours=1),
        )
        if count >= self.config.invitation_limit:
            raise TelegramLimitError
        token = self.token_generator.generate()
        expires_at = now + timedelta(minutes=15)
        await self.storage.replace_invitation(
            owner_username=owner_username,
            token_hash=token.hash,
            label=label,
            expires_at=expires_at,
            now=now,
        )
        return IssuedTelegramInvitation(
            token=token,
            bot_username=self.config.bot_username,
            expires_at=expires_at,
        )

    async def list_invitations(
        self,
        *,
        owner_username: str,
        now: datetime,
    ) -> list[TelegramInvitation]:
        return await self.storage.list_invitations(owner_username=owner_username, now=now)

    async def cancel_invitation(
        self,
        *,
        owner_username: str,
        invitation_id: str,
        now: datetime,
    ) -> None:
        await self.storage.cancel_invitation(
            owner_username=owner_username,
            invitation_id=invitation_id,
            now=now,
        )

    async def request_connection(
        self,
        *,
        token: InvitationToken,
        participant: TelegramParticipant,
        now: datetime,
    ) -> str:
        if not self.config.available:
            raise TelegramAccessError
        if self.limiter is not None and not await self.limiter.allow_attempt(
            telegram_user_id=participant.user_id,
        ):
            raise TelegramLimitError
        invitation = await self.storage.get_invitation(
            token_hash=token.hash,
            lock=True,
        )
        if invitation is None:
            raise TelegramInvitationError
        invitation.require_usable(now=now)
        if not await self.settings_reader.is_enabled(owner_username=invitation.owner_username):
            raise TelegramAccessError
        existing = await self.storage.get_connection_for_user(
            owner_username=invitation.owner_username,
            telegram_user_id=participant.user_id,
        )
        if (
            existing is not None
            and existing.state == TelegramConnectionState.PENDING
            and existing.requested_at + timedelta(hours=24) <= now
        ):
            await self.storage.set_connection_state(
                connection_id=existing.id,
                state=TelegramConnectionState.REVOKED,
                now=now,
            )
            existing = None
        if existing is not None and existing.state in (
            TelegramConnectionState.BLOCKED,
            TelegramConnectionState.PENDING,
            TelegramConnectionState.ACTIVE,
        ):
            raise TelegramAccessError
        if await self.storage.has_active_connection(telegram_user_id=participant.user_id):
            raise TelegramAccessError
        count = await self.storage.count_live_connections(
            owner_username=invitation.owner_username,
            pending_since=now - timedelta(hours=24),
        )
        if count >= self.config.connection_limit:
            raise TelegramLimitError
        await self.storage.create_pending_connection(
            owner_username=invitation.owner_username,
            participant=participant,
            label=invitation.label,
            now=now,
        )
        await self.storage.consume_invitation(invitation_id=invitation.id, now=now)
        return "pending"

    async def list_connections(self, *, owner_username: str) -> list[TelegramConnection]:
        return await self.storage.list_connections(owner_username=owner_username)

    async def approve_connection(
        self,
        *,
        owner_username: str,
        connection_id: str,
        now: datetime,
    ) -> TelegramConnection:
        connection = await self.storage.get_connection(connection_id=connection_id)
        if connection is None:
            raise TelegramAccessError
        connection.require_owner(owner_username=owner_username)
        if not self.config.available or not await self.settings_reader.is_enabled(
            owner_username=owner_username,
        ):
            raise TelegramAccessError
        if (
            connection.state != TelegramConnectionState.PENDING
            or connection.requested_at + timedelta(hours=24) <= now
        ):
            raise TelegramAccessError
        if await self.storage.has_active_connection(telegram_user_id=connection.telegram_user_id):
            raise TelegramAccessError
        return await self.storage.set_connection_state(
            connection_id=connection_id,
            state=TelegramConnectionState.ACTIVE,
            now=now,
        )

    async def change_connection_state(
        self,
        *,
        owner_username: str,
        connection_id: str,
        state: TelegramConnectionState,
        now: datetime,
    ) -> TelegramConnection:
        connection = await self.storage.get_connection(connection_id=connection_id)
        if connection is None:
            raise TelegramAccessError
        connection.require_owner(owner_username=owner_username)
        if state == TelegramConnectionState.ACTIVE:
            raise TelegramAccessError
        if state == TelegramConnectionState.PENDING:
            raise TelegramAccessError
        if (
            connection.state == TelegramConnectionState.BLOCKED
            and state == TelegramConnectionState.REVOKED
        ):
            return await self.storage.set_connection_state(
                connection_id=connection_id,
                state=state,
                now=now,
            )
        if connection.state in (
            TelegramConnectionState.PENDING,
            TelegramConnectionState.ACTIVE,
        ) and state in (TelegramConnectionState.REVOKED, TelegramConnectionState.BLOCKED):
            return await self.storage.set_connection_state(
                connection_id=connection_id,
                state=state,
                now=now,
            )
        if (
            connection.state == TelegramConnectionState.REVOKED
            and state == TelegramConnectionState.BLOCKED
        ):
            live_connection = await self.storage.get_connection_for_user(
                owner_username=owner_username,
                telegram_user_id=connection.telegram_user_id,
            )
            if live_connection is not None:
                raise TelegramAccessError
            return await self.storage.set_connection_state(
                connection_id=connection_id,
                state=state,
                now=now,
            )
        raise TelegramAccessError

    async def rename_connection(
        self,
        *,
        owner_username: str,
        connection_id: str,
        label: str,
    ) -> TelegramConnection:
        connection = await self.storage.get_connection(connection_id=connection_id)
        if connection is None:
            raise TelegramAccessError
        connection.require_owner(owner_username=owner_username)
        return await self.storage.set_connection_label(connection_id=connection_id, label=label)
