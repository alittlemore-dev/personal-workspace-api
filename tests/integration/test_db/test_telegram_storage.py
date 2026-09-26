from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from core.telegram.enums import TelegramConnectionState
from core.telegram.exceptions import TelegramInvitationError
from core.telegram.schemas import InvitationToken, TelegramParticipant, TelegramUseCaseConfig
from core.telegram.use_cases import TelegramUseCase
from infra.postgresql.storages.telegram import TelegramDatabaseStorage
from tests.test_cases import StorageTestCase

NOW = datetime(2026, 9, 26, 12, tzinfo=UTC)


class TestTelegramStorage(StorageTestCase):
    async def test_issued_link_creates_one_pending_connection_and_cannot_be_reused(self) -> None:
        reader = AsyncMock()
        reader.is_enabled.return_value = True
        generator = Mock()
        generator.generate.return_value = InvitationToken("secret")
        use_case = TelegramUseCase(
            storage=TelegramDatabaseStorage(session=self.db_session),
            settings_reader=reader,
            token_generator=generator,
            config=TelegramUseCaseConfig(
                bot_username="alittlemore_workspace_bot",
                invitation_limit=5,
                connection_limit=20,
                available=True,
            ),
            limiter=None,
        )
        issued = await use_case.create_invitation(
            owner_username="auth-user-without-local-row",
            label="Family",
            now=NOW,
        )
        participant = TelegramParticipant(
            user_id=42,
            private_chat_id=42,
            first_name="Boris",
            username="boris",
        )

        assert issued.url == "https://t.me/alittlemore_workspace_bot?start=secret"
        assert (
            await use_case.request_connection(
                token=issued.token,
                participant=participant,
                now=NOW,
            )
            == "pending"
        )
        connections = await use_case.list_connections(owner_username="auth-user-without-local-row")
        assert len(connections) == 1
        assert connections[0].private_chat_id == 42
        with pytest.raises(TelegramInvitationError):
            await use_case.request_connection(
                token=issued.token,
                participant=participant,
                now=NOW,
            )

    async def test_invitation_and_chat_connection_live_in_workspace_without_local_user(
        self,
    ) -> None:
        storage = TelegramDatabaseStorage(session=self.db_session)
        assert (
            await storage.count_recent_invitations(
                owner_username="auth-user-without-local-row",
                since=NOW - timedelta(hours=1),
            )
            == 0
        )
        invitation = await storage.replace_invitation(
            owner_username="auth-user-without-local-row",
            token_hash=InvitationToken("secret").hash,
            label="Family",
            expires_at=NOW + timedelta(minutes=15),
            now=NOW,
        )

        loaded = await storage.get_invitation(
            token_hash=InvitationToken("secret").hash,
            lock=True,
        )
        assert loaded == invitation
        connection = await storage.create_pending_connection(
            owner_username=invitation.owner_username,
            participant=TelegramParticipant(
                user_id=42,
                private_chat_id=42,
                first_name="Boris",
                username="boris",
            ),
            label=invitation.label,
            now=NOW,
        )
        await storage.consume_invitation(invitation_id=invitation.id, now=NOW)
        consumed = await storage.get_invitation(token_hash=invitation.token_hash, lock=False)
        assert consumed is not None
        assert consumed.used_at == NOW
        assert (
            await storage.list_invitations(owner_username=invitation.owner_username, now=NOW) == []
        )
        assert (await storage.list_connections(owner_username=invitation.owner_username)) == [
            connection,
        ]
        approved = await storage.set_connection_state(
            connection_id=connection.id,
            state=TelegramConnectionState.ACTIVE,
            now=NOW,
        )
        assert approved.state == TelegramConnectionState.ACTIVE
        assert await storage.has_active_connection(telegram_user_id=42)
