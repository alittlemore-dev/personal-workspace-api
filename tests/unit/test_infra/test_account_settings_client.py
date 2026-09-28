# ruff: noqa: S106
from zoneinfo import ZoneInfo

import httpx
import pytest

from core.account_time_zone.clients import AccountTimeZoneUnavailableError
from core.telegram.exceptions import TelegramServiceError
from infra.auth.account_settings_client import (
    AccountSettingsClientConfig,
    AuthAccountSettingsReader,
)


def account_settings(*, time_zone: str, enabled: bool, notify: bool) -> dict[str, object]:
    return {
        "language": "en",
        "theme": "system",
        "timeZone": time_zone,
        "telegramBots": {"personal-workspace": {"enabled": enabled, "notify": notify}},
    }


def make_reader(
    *,
    transport: httpx.MockTransport,
    telegram_available: bool,
) -> tuple[httpx.AsyncClient, AuthAccountSettingsReader]:
    http_client = httpx.AsyncClient(transport=transport)
    reader = AuthAccountSettingsReader(
        http_client=http_client,
        config=AccountSettingsClientConfig(
            url="http://auth-api:8080/api/auth/internal/account",
            service_secret="test-service-secret",
            telegram_available=telegram_available,
        ),
    )
    return http_client, reader


@pytest.mark.asyncio
async def test_generic_account_settings_route_and_zone_conversion() -> None:
    captured: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json=account_settings(time_zone="Asia/Yerevan", enabled=True, notify=True),
        )

    http_client, reader = make_reader(
        transport=httpx.MockTransport(respond),
        telegram_available=True,
    )
    async with http_client:
        assert await reader.get_time_zone(owner_username="anna@example.com") == ZoneInfo(
            "Asia/Yerevan",
        )
        assert await reader.can_notify(owner_username="anna@example.com")

    assert captured[0].url.raw_path.endswith(b"/anna%40example.com/settings")
    assert captured[0].headers["X-Internal-Service-Secret"] == "test-service-secret"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "payload"),
    [
        (404, {"detail": "Not found"}),
        (200, {}),
        (200, account_settings(time_zone="Not/AZone", enabled=True, notify=True)),
    ],
)
async def test_account_settings_reader_fails_closed(
    status: int,
    payload: dict[str, object],
) -> None:
    http_client, reader = make_reader(
        transport=httpx.MockTransport(lambda _request: httpx.Response(status, json=payload)),
        telegram_available=True,
    )
    async with http_client:
        with pytest.raises(AccountTimeZoneUnavailableError):
            await reader.get_time_zone(owner_username="anna")
        with pytest.raises(TelegramServiceError):
            await reader.can_notify(owner_username="anna")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("enabled", "notify", "available", "expected"),
    [
        (True, True, True, True),
        (True, False, True, False),
        (False, True, True, False),
        (True, True, False, False),
    ],
)
async def test_telegram_policy_combines_account_settings_and_local_availability(
    enabled: bool,
    notify: bool,
    available: bool,
    expected: bool,
) -> None:
    payload = account_settings(time_zone="UTC", enabled=enabled, notify=notify)
    http_client, reader = make_reader(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload)),
        telegram_available=available,
    )
    async with http_client:
        assert await reader.can_notify(owner_username="anna") is expected
        assert await reader.is_enabled(owner_username="anna") is (available and enabled)


@pytest.mark.asyncio
async def test_missing_bot_preference_disables_bot_without_failing_account_zone() -> None:
    payload = account_settings(time_zone="UTC", enabled=True, notify=True)
    payload["telegramBots"] = {}
    http_client, reader = make_reader(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload)),
        telegram_available=True,
    )
    async with http_client:
        assert await reader.get_time_zone(owner_username="anna") == ZoneInfo("UTC")
        assert not await reader.is_enabled(owner_username="anna")
        assert not await reader.can_notify(owner_username="anna")
