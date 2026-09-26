from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from core.telegram.exceptions import TelegramLimitError
from core.telegram.schemas import InvitationToken, TelegramParticipant, TelegramUseCaseConfig
from core.telegram.use_cases import TelegramUseCase


@pytest.mark.asyncio
async def test_rate_limit_prevents_invitation_lookup() -> None:
    limiter = AsyncMock()
    limiter.allow_attempt.return_value = False
    storage = AsyncMock()
    use_case = TelegramUseCase(
        storage=storage,
        settings_reader=AsyncMock(),
        token_generator=Mock(),
        config=TelegramUseCaseConfig(
            bot_username="alittlemore_workspace_bot",
            invitation_limit=5,
            connection_limit=20,
            available=True,
        ),
        limiter=limiter,
    )

    with pytest.raises(TelegramLimitError):
        await use_case.request_connection(
            token=InvitationToken("token"),
            participant=TelegramParticipant(
                user_id=42,
                private_chat_id=42,
                first_name="Boris",
                username="boris",
            ),
            now=datetime(2026, 9, 26, tzinfo=UTC),
        )

    storage.get_invitation.assert_not_awaited()
