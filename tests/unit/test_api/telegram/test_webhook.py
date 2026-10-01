from unittest.mock import AsyncMock, Mock

import pytest
from backend_sdk.auth.testing import FakeAuthenticationClient
from backend_sdk.integrations.litestar import AuthPlugin
from dishka import AsyncContainer
from litestar.testing import TestClient

from core.telegram.enums import TelegramRuntimeStatus
from entrypoints.litestar.initializers.main import create_litestar_app
from infra.config.settings import settings
from infra.valkey.telegram_runtime import TelegramRuntimeStatusStore


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
    client.app.state.telegram_runtime_state.status = TelegramRuntimeStatus.READY
    store = Mock(spec=TelegramRuntimeStatusStore)
    store.is_ready = AsyncMock(return_value=True)
    client.app.state.telegram_runtime_status = store
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


def test_polling_mode_rejects_webhook_without_dispatching(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings.telegram, "delivery_mode", "polling")
    dispatcher = AsyncMock()
    client.app.state.telegram_dispatcher = dispatcher
    response = client.post(
        "/api/telegram/webhook",
        json={"update_id": 42},
        headers={"X-Telegram-Bot-Api-Secret-Token": "TEST_WEBHOOK_SECRET"},
    )
    assert response.status_code == 503
    dispatcher.feed_raw_update.assert_not_awaited()


@pytest.mark.parametrize("runtime_status", ["connecting", "failed", "disabled", "ready"])
def test_unready_webhook_rejects_updates_without_dispatching(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    runtime_status: str,
) -> None:
    dispatcher = AsyncMock()
    client.app.state.telegram_dispatcher = dispatcher
    client.app.state.telegram_runtime_state.status = TelegramRuntimeStatus(runtime_status)
    store = Mock(spec=TelegramRuntimeStatusStore)
    store.is_ready = AsyncMock(return_value=False)
    client.app.state.telegram_runtime_status = store
    monkeypatch.setattr(settings.telegram, "available", True)
    response = client.post(
        "/api/telegram/webhook",
        json={"update_id": 42},
        headers={"X-Telegram-Bot-Api-Secret-Token": "TEST_WEBHOOK_SECRET"},
    )
    assert response.status_code == 503
    dispatcher.feed_raw_update.assert_not_awaited()


def test_runtime_status_requires_service_secret_and_is_minimal(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings.telegram, "available", True)
    client.app.state.telegram_runtime_state.status = TelegramRuntimeStatus.CONNECTING
    for supplied in ("", "wrong"):
        response = client.get(
            "/api/internal/telegram/status",
            headers={"X-Telegram-Service-Secret": supplied},
        )
        assert response.status_code == 403
    response = client.get(
        "/api/internal/telegram/status",
        headers={"X-Telegram-Service-Secret": settings.telegram.service_secret.get_secret_value()},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "connecting"}
    assert response.headers["cache-control"] == "no-store"


def test_internal_status_does_not_report_ready_after_worker_invalidates_lease(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings.telegram, "available", True)
    client.app.state.telegram_runtime_state.status = TelegramRuntimeStatus.READY
    store = Mock(spec=TelegramRuntimeStatusStore)
    store.is_ready = AsyncMock(return_value=False)
    client.app.state.telegram_runtime_status = store
    response = client.get(
        "/api/internal/telegram/status",
        headers={"X-Telegram-Service-Secret": settings.telegram.service_secret.get_secret_value()},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "failed"}


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
