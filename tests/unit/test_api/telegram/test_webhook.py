from unittest.mock import AsyncMock

import pytest
from backend_sdk.auth.testing import FakeAuthenticationClient
from backend_sdk.integrations.litestar import AuthPlugin
from dishka import AsyncContainer
from litestar.testing import TestClient

from entrypoints.litestar.initializers.main import create_litestar_app
from infra.config.settings import settings


def test_wrong_webhook_secret_is_rejected_before_json_parse(client: TestClient) -> None:
    response = client.post(
        "/api/telegram/webhook",
        content=b"not json",
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong", "Content-Type": "application/json"},
    )
    assert response.status_code == 403


def test_valid_webhook_forwards_update_to_dispatcher(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatcher = AsyncMock()
    client.app.state.telegram_dispatcher = dispatcher
    monkeypatch.setattr(settings.telegram, "available", True)
    response = client.post(
        "/api/telegram/webhook",
        json={"update_id": 42, "message": {"message_id": 1}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "TEST_WEBHOOK_SECRET"},
    )
    assert response.status_code == 200
    dispatcher.feed_raw_update.assert_awaited_once_with(
        {"update_id": 42, "message": {"message_id": 1}},
    )


def test_webhook_allows_anonymous_telegram_but_management_requires_account(
    container: AsyncContainer,
) -> None:
    app = create_litestar_app(
        lifespan=[],
        container=container,
        extra_plugins=[AuthPlugin(auth_client=FakeAuthenticationClient())],
        extra_middlewares=[],
    )
    with TestClient(app) as client:
        webhook = client.post(
            "/api/telegram/webhook",
            json={"update_id": 1},
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        )
        management = client.get("/api/telegram")

    assert webhook.status_code == 403
    assert management.status_code == 401
