# ruff: noqa: S106
import httpx
import pytest

from core.telegram.exceptions import TelegramServiceError
from infra.telegram.auth_api_client import (
    TelegramAuthApiClientConfig,
    TelegramAuthApiSettingsReader,
)


@pytest.mark.asyncio
async def test_settings_reader_uses_internal_auth_api_and_service_secret() -> None:
    captured: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"available": True, "enabled": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        reader = TelegramAuthApiSettingsReader(
            http_client=http_client,
            config=TelegramAuthApiClientConfig(
                url="http://auth-api:8080/api/auth/internal/telegram/personal-workspace/settings",
                service_secret="test-service-secret",
            ),
        )
        result = await reader.is_enabled(owner_username="anna")

    assert result
    assert captured[0].headers["X-Telegram-Service-Secret"] == "test-service-secret"
    assert captured[0].url.path == "/api/auth/internal/telegram/personal-workspace/settings"
    assert b'"ownerUsername":"anna"' in captured[0].content


@pytest.mark.asyncio
async def test_settings_reader_fails_closed_on_invalid_auth_response() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=[])),
    ) as http_client:
        reader = TelegramAuthApiSettingsReader(
            http_client=http_client,
            config=TelegramAuthApiClientConfig(
                url="http://auth-api:8080/api/auth/internal/telegram/personal-workspace/settings",
                service_secret="test-service-secret",
            ),
        )
        with pytest.raises(TelegramServiceError):
            await reader.is_enabled(owner_username="anna")
