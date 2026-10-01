from datetime import UTC, datetime
from typing import cast
from unittest.mock import Mock

import pytest
import pytest_asyncio
from httpx import codes

from core.i18n.enums import LanguageEnum
from core.telegram.enums import TelegramRuntimeStatus
from core.telegram.schemas import (
    CreateTelegramInvitationParams,
    InvitationToken,
    IssuedTelegramInvitation,
    SetTelegramConnectionSettingsParams,
    TelegramConnectionSettings,
)
from core.telegram.use_cases import TelegramUseCase
from infra.config.settings import settings
from tests.test_cases import ApiTestCase

NOW = datetime(2026, 7, 27, 12, tzinfo=UTC)


class TestTelegramManagementApi(ApiTestCase):
    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.use_case = cast("Mock", await self.container.container.get(TelegramUseCase))
        monkeypatch.setattr(settings.telegram, "available", True)
        self.api.client.app.state.telegram_runtime_state.status = TelegramRuntimeStatus.READY

    def test_lists_connections_and_bot_availability(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings.telegram, "available", True)
        self.use_case.list_invitations.return_value = []
        self.use_case.list_connections.return_value = []

        response = self.api.client.get("/api/telegram")

        self.asserts.status(response=response, expected_status=codes.OK)
        assert response.json() == {
            "available": True,
            "status": "ready",
            "invitations": [],
            "connections": [],
        }

    @pytest.mark.parametrize("runtime_status", ["connecting", "failed", "disabled"])
    def test_unready_bot_blocks_all_mutations_and_keeps_settings_readable(
        self,
        runtime_status: str,
    ) -> None:
        self.api.client.app.state.telegram_runtime_state.status = TelegramRuntimeStatus(
            runtime_status,
        )
        self.use_case.list_invitations.return_value = []
        self.use_case.list_connections.return_value = []
        response = self.api.client.get("/api/telegram")
        assert response.status_code == 200
        assert response.json()["status"] == runtime_status
        for method, path, payload in (
            ("POST", "/invitations", {"label": "Family"}),
            ("DELETE", "/invitations/example", None),
            ("POST", "/connections/example/approve", {}),
            ("POST", "/connections/example/revoke", {}),
            ("POST", "/connections/example/block", {}),
            ("POST", "/connections/example/unblock", {}),
            ("PUT", "/connections/example/label", {"label": "Family"}),
            ("PUT", "/connections/example/settings", {}),
        ):
            response = self.api.client.request(method, f"/api/telegram{path}", json=payload)
            assert response.status_code == 503
        self.use_case.create_invitation.assert_not_awaited()
        self.use_case.cancel_invitation.assert_not_awaited()
        self.use_case.approve_connection.assert_not_awaited()
        self.use_case.change_connection_state.assert_not_awaited()
        self.use_case.rename_connection.assert_not_awaited()
        self.use_case.set_connection_settings.assert_not_awaited()

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
            params=CreateTelegramInvitationParams(
                owner_username="test-owner",
                label="Family",
                now=NOW,
            ),
        )

    def test_blank_invitation_label_is_rejected_before_use_case(self) -> None:
        response = self.api.client.post(
            "/api/telegram/invitations",
            json={"label": "   "},
        )

        self.asserts.status(response=response, expected_status=codes.BAD_REQUEST)
        self.use_case.create_invitation.assert_not_awaited()

    def test_connection_settings_require_complete_valid_payload(self) -> None:
        for payload in (
            {"notifyBirthday": True, "notifyMemorableDate": False},
            {
                "notifyBirthday": True,
                "notifyMemorableDate": False,
                "language": "invalid",
            },
        ):
            response = self.api.client.put(
                "/api/telegram/connections/connection-id/settings",
                json=payload,
            )
            self.asserts.status(response=response, expected_status=codes.BAD_REQUEST)
        self.use_case.set_connection_settings.assert_not_awaited()

    def test_finance_subscriptions_are_saved_independently_and_returned(self) -> None:
        self.use_case.set_connection_settings.return_value = self.factory.core.telegram_connection(
            owner_username="test-owner",
            notify_finance_transaction=True,
            notify_finance_limit=False,
        )
        response = self.api.client.put(
            "/api/telegram/connections/connection-id/settings",
            json={
                "notifyBirthday": False,
                "notifyMemorableDate": False,
                "notifyFinanceTransaction": True,
                "notifyFinanceLimit": False,
                "language": "ru",
            },
        )
        self.asserts.status(response=response, expected_status=codes.OK)
        assert response.json()["notifyFinanceTransaction"] is True
        assert response.json()["notifyFinanceLimit"] is False
        self.use_case.set_connection_settings.assert_awaited_once_with(
            params=SetTelegramConnectionSettingsParams(
                owner_username="test-owner",
                connection_id="connection-id",
                settings=TelegramConnectionSettings(
                    notify_birthday=False,
                    notify_memorable_date=False,
                    notify_finance_transaction=True,
                    notify_finance_limit=False,
                    language=LanguageEnum.RU,
                ),
            ),
        )
