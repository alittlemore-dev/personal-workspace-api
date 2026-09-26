from datetime import UTC, datetime
from unittest.mock import patch

from core.telegram.generators import InvitationTokenGenerator
from core.telegram.schemas import InvitationToken, IssuedTelegramInvitation


def test_generator_returns_token_with_cryptographic_hash() -> None:
    with patch("core.telegram.generators.secrets.token_urlsafe", return_value="abc"):
        token = InvitationTokenGenerator().generate()

    assert type(token) is InvitationToken
    assert token.hash == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_issued_invitation_builds_url_without_exposing_token_in_repr() -> None:
    issued = IssuedTelegramInvitation(
        token=InvitationToken("abc"),
        bot_username="alittlemore_workspace_bot",
        expires_at=datetime(2026, 9, 26, tzinfo=UTC),
    )

    assert issued.url == "https://t.me/alittlemore_workspace_bot?start=abc"
    assert "abc" not in repr(issued)
