from datetime import UTC, datetime
from typing import cast
from unittest.mock import Mock

import pytest
import pytest_asyncio
from httpx import codes

from core.telegram.schemas import InvitationToken, IssuedTelegramInvitation
from core.telegram.use_cases import TelegramUseCase
from infra.config.settings import settings
from tests.test_cases import ApiTestCase

NOW = datetime(2026, 7, 27, 12, tzinfo=UTC)


class TestTelegramManagementApi(ApiTestCase):
    @pytest_asyncio.fixture(autouse=True)
    async def setup(self) -> None:
        self.use_case = cast("Mock", await self.container.container.get(TelegramUseCase))

    def test_lists_connections_and_bot_availability(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings.telegram, "available", True)
        self.use_case.list_invitations.return_value = []
        self.use_case.list_connections.return_value = []

        response = self.api.client.get("/api/telegram")

        self.asserts.status(response=response, expected_status=codes.OK)
        assert response.json() == {"available": True, "invitations": [], "connections": []}

    def test_issue_invitation_scopes_owner_and_returns_no_store_link(self) -> None:
        self.use_case.create_invitation.return_value = IssuedTelegramInvitation(
            token=InvitationToken("secret"),
            bot_username="alittlemore_workspace_bot",
            expires_at=NOW,
        )

        response = self.api.client.post(
            "/api/telegram/invitations",
            json={"label": "Family"},
        )

        self.asserts.status(response=response, expected_status=codes.CREATED)
        assert response.json()["url"] == "https://t.me/alittlemore_workspace_bot?start=secret"
        assert response.headers["cache-control"] == "no-store"
        self.use_case.create_invitation.assert_awaited_once_with(
            owner_username="test-owner",
            label="Family",
            now=NOW,
        )

    def test_blank_invitation_label_is_rejected_before_use_case(self) -> None:
        response = self.api.client.post(
            "/api/telegram/invitations",
            json={"label": "   "},
        )

        self.asserts.status(response=response, expected_status=codes.BAD_REQUEST)
        self.use_case.create_invitation.assert_not_awaited()
