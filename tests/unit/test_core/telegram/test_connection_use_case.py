from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from core.telegram.exceptions import TelegramAccessError
from core.telegram.schemas import InvitationToken, TelegramUseCaseConfig
from core.telegram.use_cases import TelegramUseCase

NOW = datetime(2026, 9, 26, 12, tzinfo=UTC)


@pytest.mark.asyncio
async def test_issues_single_use_invitation_only_for_enabled_owner() -> None:
    storage = AsyncMock()
    storage.count_recent_invitations.return_value = 0
    reader = AsyncMock()
    reader.is_enabled.return_value = True
    generator = Mock()
    generator.generate.return_value = InvitationToken("secret")
    use_case = TelegramUseCase(
        storage=storage,
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

    issued = await use_case.create_invitation(owner_username="anna", label="Family", now=NOW)

    assert issued.url == "https://t.me/alittlemore_workspace_bot?start=secret"
    reader.is_enabled.assert_awaited_once_with(owner_username="anna")
    storage.replace_invitation.assert_awaited_once()
    assert (
        storage.replace_invitation.call_args.kwargs["token_hash"] == InvitationToken("secret").hash
    )

    reader.is_enabled.return_value = False
    with pytest.raises(TelegramAccessError):
        await use_case.create_invitation(owner_username="anna", label="Family", now=NOW)
