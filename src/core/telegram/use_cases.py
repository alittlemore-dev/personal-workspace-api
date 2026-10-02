from dataclasses import dataclass
from datetime import timedelta

from core.telegram.enums import TelegramConnectionState
from core.telegram.exceptions import (
    TelegramAccessError,
    TelegramInvitationError,
    TelegramLimitError,
)
from core.telegram.generators import InvitationTokenGenerator
from core.telegram.schemas import (
    ApproveTelegramConnectionParams,
    CancelTelegramInvitationParams,
    ChangeTelegramConnectionStateParams,
    CreateTelegramInvitationParams,
    IssuedTelegramInvitation,
    ListTelegramInvitationsParams,
    RenameTelegramConnectionParams,
    RequestTelegramConnectionParams,
    ResolveTelegramConnectionParams,
    SetTelegramConnectionSettingsParams,
    TelegramConnection,
    TelegramInvitation,
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

    async def resolve_active_connection(
        self,
        *,
        params: ResolveTelegramConnectionParams,
    ) -> TelegramConnection:
        if not self.config.available:
            raise TelegramAccessError
        connection = await self.storage.active_connection_for_participant(
            telegram_user_id=params.telegram_user_id,
            private_chat_id=params.private_chat_id,
            lock=False,
        )
        if connection is None or not await self.settings_reader.is_enabled(
            owner_username=connection.owner_username,
        ):
            raise TelegramAccessError
        return connection

    async def create_invitation(
        self,
        *,
        params: CreateTelegramInvitationParams,
    ) -> IssuedTelegramInvitation:
        if not self.config.available or not await self.settings_reader.is_enabled(
            owner_username=params.owner_username,
        ):
            raise TelegramAccessError
        count = await self.storage.count_recent_invitations(
            owner_username=params.owner_username,
            since=params.now - timedelta(hours=1),
        )
        if count >= self.config.invitation_limit:
            raise TelegramLimitError
        token = self.token_generator.generate()
        expires_at = params.now + timedelta(minutes=15)
        await self.storage.replace_invitation(
            owner_username=params.owner_username,
            token_hash=token.hash,
            label=params.label,
            expires_at=expires_at,
            now=params.now,
        )
        return IssuedTelegramInvitation(
            token=token,
            bot_username=self.config.bot_username,
            expires_at=expires_at,
        )

    async def list_invitations(
        self,
        *,
        params: ListTelegramInvitationsParams,
    ) -> list[TelegramInvitation]:
        return await self.storage.list_invitations(
            owner_username=params.owner_username,
            now=params.now,
        )

    async def cancel_invitation(self, *, params: CancelTelegramInvitationParams) -> None:
        await self.storage.cancel_invitation(
            owner_username=params.owner_username,
            invitation_id=params.invitation_id,
            now=params.now,
        )

    async def request_connection(self, *, params: RequestTelegramConnectionParams) -> str:
        if not self.config.available:
            raise TelegramAccessError
        if self.limiter is not None and not await self.limiter.allow_attempt(
            telegram_user_id=params.participant.user_id,
        ):
            raise TelegramLimitError
        invitation = await self.storage.get_invitation(
            token_hash=params.token.hash,
            lock=True,
        )
        if invitation is None:
            raise TelegramInvitationError
        invitation.require_usable(now=params.now)
        if not await self.settings_reader.is_enabled(owner_username=invitation.owner_username):
            raise TelegramAccessError
        existing = await self.storage.get_connection_for_user(
            owner_username=invitation.owner_username,
            telegram_user_id=params.participant.user_id,
        )
        if (
            existing is not None
            and existing.state == TelegramConnectionState.PENDING
            and existing.requested_at + timedelta(hours=24) <= params.now
        ):
            await self.storage.set_connection_state(
                connection_id=existing.id,
                state=TelegramConnectionState.REVOKED,
                now=params.now,
            )
            existing = None
        if existing is not None and existing.state in (
            TelegramConnectionState.BLOCKED,
            TelegramConnectionState.PENDING,
            TelegramConnectionState.ACTIVE,
        ):
            raise TelegramAccessError
        if await self.storage.has_active_connection(telegram_user_id=params.participant.user_id):
            raise TelegramAccessError
        count = await self.storage.count_live_connections(
            owner_username=invitation.owner_username,
            pending_since=params.now - timedelta(hours=24),
        )
        if count >= self.config.connection_limit:
            raise TelegramLimitError
        await self.storage.create_pending_connection(
            owner_username=invitation.owner_username,
            participant=params.participant,
            label=invitation.label,
            now=params.now,
        )
        await self.storage.consume_invitation(invitation_id=invitation.id, now=params.now)
        return "pending"

    async def list_connections(self, *, owner_username: str) -> list[TelegramConnection]:
        return await self.storage.list_connections(owner_username=owner_username)

    async def approve_connection(
        self,
        *,
        params: ApproveTelegramConnectionParams,
    ) -> TelegramConnection:
        connection = await self.storage.get_connection(connection_id=params.connection_id)
        if connection is None:
            raise TelegramAccessError
        connection.require_owner(owner_username=params.owner_username)
        if not self.config.available or not await self.settings_reader.is_enabled(
            owner_username=params.owner_username,
        ):
            raise TelegramAccessError
        if (
            connection.state != TelegramConnectionState.PENDING
            or connection.requested_at + timedelta(hours=24) <= params.now
        ):
            raise TelegramAccessError
        if await self.storage.has_active_connection(telegram_user_id=connection.telegram_user_id):
            raise TelegramAccessError
        return await self.storage.set_connection_state(
            connection_id=params.connection_id,
            state=TelegramConnectionState.ACTIVE,
            now=params.now,
        )

    async def change_connection_state(
        self,
        *,
        params: ChangeTelegramConnectionStateParams,
    ) -> TelegramConnection:
        connection = await self.storage.get_connection(connection_id=params.connection_id)
        if connection is None:
            raise TelegramAccessError
        connection.require_owner(owner_username=params.owner_username)
        if params.state == TelegramConnectionState.ACTIVE:
            raise TelegramAccessError
        if params.state == TelegramConnectionState.PENDING:
            raise TelegramAccessError
        if (
            connection.state == TelegramConnectionState.BLOCKED
            and params.state == TelegramConnectionState.REVOKED
        ):
            return await self.storage.set_connection_state(
                connection_id=params.connection_id,
                state=params.state,
                now=params.now,
            )
        if connection.state in (
            TelegramConnectionState.PENDING,
            TelegramConnectionState.ACTIVE,
        ) and params.state in (TelegramConnectionState.REVOKED, TelegramConnectionState.BLOCKED):
            return await self.storage.set_connection_state(
                connection_id=params.connection_id,
                state=params.state,
                now=params.now,
            )
        if (
            connection.state == TelegramConnectionState.REVOKED
            and params.state == TelegramConnectionState.BLOCKED
        ):
            live_connection = await self.storage.get_connection_for_user(
                owner_username=params.owner_username,
                telegram_user_id=connection.telegram_user_id,
            )
            if live_connection is not None:
                raise TelegramAccessError
            return await self.storage.set_connection_state(
                connection_id=params.connection_id,
                state=params.state,
                now=params.now,
            )
        raise TelegramAccessError

    async def rename_connection(
        self,
        *,
        params: RenameTelegramConnectionParams,
    ) -> TelegramConnection:
        connection = await self.storage.get_connection(connection_id=params.connection_id)
        if connection is None:
            raise TelegramAccessError
        connection.require_owner(owner_username=params.owner_username)
        return await self.storage.set_connection_label(
            connection_id=params.connection_id,
            label=params.label,
        )

    async def set_connection_settings(
        self,
        *,
        params: SetTelegramConnectionSettingsParams,
    ) -> TelegramConnection:
        connection = await self.storage.get_connection(connection_id=params.connection_id)
        if connection is None:
            raise TelegramAccessError
        connection.require_owner(owner_username=params.owner_username)
        return await self.storage.set_connection_settings(
            connection_id=params.connection_id,
            settings=params.settings,
        )
