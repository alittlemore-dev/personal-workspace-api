import asyncio
from collections.abc import AsyncGenerator
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)
from aiogram.methods import GetMe, SendMessage
from aiogram.types import User
from aiohttp_socks import ProxyConnectionError, ProxyError, ProxyTimeoutError
from valkey.exceptions import ConnectionError as ValkeyConnectionError

from infra.config.settings import SecretStrExtended, settings
from infra.telegram.bot import TelegramFailoverSession, create_telegram_bot
from infra.valkey.telegram_runtime import TelegramRuntimeStatusStore

TEST_BOT_TOKEN = "123456:TEST_TOKEN"  # noqa: S105 - deterministic test-only credential


@pytest.fixture
def transport() -> TelegramFailoverSession:
    config = settings.telegram.model_copy(
        update={
            "proxy_urls": [
                SecretStrExtended("http://primary.test:8080"),
                SecretStrExtended("socks5://backup.test:1080"),
            ],
        },
    )
    store = Mock(spec=TelegramRuntimeStatusStore)
    store.get_ready_route = AsyncMock(return_value=0)
    store.mark_failed = AsyncMock(return_value=True)
    store.close = AsyncMock()
    bot = create_telegram_bot(telegram_settings=config, runtime_status=store)
    assert isinstance(bot.session, TelegramFailoverSession)
    return bot.session


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    ["network", "timeout", "server", "proxy-connection", "proxy-timeout", "proxy-protocol"],
)
async def test_failed_send_has_one_attempt_invalidates_route_and_wakes_monitor(
    transport: TelegramFailoverSession,
    monkeypatch: pytest.MonkeyPatch,
    error: str,
) -> None:
    method = SendMessage(chat_id=123, text="One attempt")
    failures = {
        "network": TelegramNetworkError(method=method, message="network"),
        "timeout": TimeoutError(),
        "server": TelegramServerError(method=method, message="server"),
        "proxy-connection": ProxyConnectionError("PRIVATE_PROXY_PASSWORD"),
        "proxy-timeout": ProxyTimeoutError("PRIVATE_PROXY_PASSWORD"),
        "proxy-protocol": ProxyError("PRIVATE_PROXY_PASSWORD"),
    }
    primary = AsyncMock(side_effect=failures[error])
    backup = AsyncMock()
    monkeypatch.setattr(transport.routes[0], "make_request", primary)
    monkeypatch.setattr(transport.routes[1], "make_request", backup)
    bot = Bot(token=TEST_BOT_TOKEN, session=transport)
    expected = TelegramNetworkError if error.startswith("proxy-") else type(failures[error])
    with pytest.raises(expected) as caught:
        await bot(method)
    assert "PRIVATE_PROXY_PASSWORD" not in str(caught.value)
    primary.assert_awaited_once()
    backup.assert_not_awaited()
    cast("Mock", transport.runtime_status).mark_failed.assert_awaited_once_with(0)
    assert transport.wake.is_set()
    assert not transport.candidate_available(0)
    assert transport.candidate_available(1)
    with pytest.raises(TelegramNetworkError):
        await bot(method)
    assert primary.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ProxyConnectionError, ProxyTimeoutError, ProxyError])
async def test_proxy_probe_failure_enters_cooldown_without_waiting_for_retry_cycle(
    transport: TelegramFailoverSession,
    monkeypatch: pytest.MonkeyPatch,
    error: type[Exception],
) -> None:
    monkeypatch.setattr(
        transport.routes[0],
        "make_request",
        AsyncMock(side_effect=error("PRIVATE_PROXY_PASSWORD")),
    )
    with pytest.raises(TelegramNetworkError) as caught:
        await transport.probe(Bot(token=TEST_BOT_TOKEN, session=transport), 0)
    assert "PRIVATE_PROXY_PASSWORD" not in str(caught.value)
    assert not transport.candidate_available(0)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ProxyConnectionError, ProxyTimeoutError, ProxyError])
async def test_proxy_download_failure_invalidates_route_without_replaying(
    transport: TelegramFailoverSession,
    monkeypatch: pytest.MonkeyPatch,
    error: type[Exception],
) -> None:
    async def failed_stream(*_: object, **__: object) -> AsyncGenerator[bytes]:
        yield b"partial content"
        message = "PRIVATE_PROXY_PASSWORD"
        raise error(message)

    monkeypatch.setattr(transport.routes[0], "stream_content", failed_stream)
    backup = Mock()
    monkeypatch.setattr(transport.routes[1], "stream_content", backup)
    with pytest.raises(OSError, match="Telegram proxy transport failed") as caught:
        _ = [chunk async for chunk in transport.stream_content("https://files.test/content")]
    assert "PRIVATE_PROXY_PASSWORD" not in str(caught.value)
    backup.assert_not_called()
    cast("Mock", transport.runtime_status).mark_failed.assert_awaited_once_with(0)
    assert transport.wake.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", ["rate_limit", "token", "domain"])
async def test_api_errors_do_not_cycle_routes_or_create_cooldowns(
    transport: TelegramFailoverSession,
    monkeypatch: pytest.MonkeyPatch,
    error: str,
) -> None:
    method = SendMessage(chat_id=123, text="One attempt")
    failures = {
        "rate_limit": TelegramRetryAfter(method=method, message="rate limit", retry_after=30),
        "token": TelegramUnauthorizedError(method=method, message="token"),
        "domain": TelegramBadRequest(method=method, message="domain"),
    }
    monkeypatch.setattr(transport.routes[0], "make_request", AsyncMock(side_effect=failures[error]))
    monkeypatch.setattr(transport.routes[1], "make_request", AsyncMock())
    with pytest.raises(type(failures[error])):
        await transport.make_request(Bot(token=TEST_BOT_TOKEN, session=transport), method)
    cast("Mock", transport.runtime_status).mark_failed.assert_not_awaited()
    cast("AsyncMock", transport.routes[1].make_request).assert_not_awaited()
    assert not transport.wake.is_set()
    assert transport.candidate_available(0)


@pytest.mark.asyncio
async def test_concurrent_request_keeps_its_session_when_shared_route_changes(
    transport: TelegramFailoverSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    user = User(id=123456, is_bot=True, first_name="Test")

    async def primary(*_: object, **__: object) -> User:
        entered.set()
        await release.wait()
        return user

    monkeypatch.setattr(transport.routes[0], "make_request", AsyncMock(side_effect=primary))
    monkeypatch.setattr(transport.routes[1], "make_request", AsyncMock(return_value=user))
    bot = Bot(token=TEST_BOT_TOKEN, session=transport)
    first = asyncio.create_task(bot.get_me())
    await entered.wait()
    cast("Mock", transport.runtime_status).get_ready_route.return_value = 1
    assert (await bot.get_me()).id == user.id
    release.set()
    assert (await first).id == user.id
    cast("AsyncMock", transport.routes[0].make_request).assert_awaited_once()
    cast("AsyncMock", transport.routes[1].make_request).assert_awaited_once()
    assert str(transport.routes[0].proxy).startswith("http://primary.test:")
    assert str(transport.routes[1].proxy).startswith("socks5://backup.test:")


@pytest.mark.asyncio
async def test_probe_bypasses_ready_gate_but_real_calls_fail_closed(
    transport: TelegramFailoverSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cast("Mock", transport.runtime_status).get_ready_route.return_value = None
    monkeypatch.setattr(
        transport.routes[1],
        "make_request",
        AsyncMock(
            return_value=User(id=123456, is_bot=True, first_name="Test"),
        ),
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=transport)
    with pytest.raises(TelegramNetworkError):
        await bot.get_me()
    assert (await transport.probe(bot, 1)).id == 123456
    cast("AsyncMock", transport.routes[1].make_request).assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_send_preserves_original_error_if_store_is_down(
    transport: TelegramFailoverSession,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    method = GetMe()
    monkeypatch.setattr(
        transport.routes[0],
        "make_request",
        AsyncMock(
            side_effect=TelegramNetworkError(method=method, message="original error"),
        ),
    )
    cast("Mock", transport.runtime_status).mark_failed.side_effect = ValkeyConnectionError(
        "PRIVATE_TOKEN",
    )
    with pytest.raises(TelegramNetworkError, match="original error"):
        await transport.make_request(Bot(token=TEST_BOT_TOKEN, session=transport), method)
    assert not transport.candidate_available(0)
    assert "PRIVATE_TOKEN" not in capsys.readouterr().out


@pytest.mark.asyncio
async def test_close_releases_all_route_sessions_without_closing_external_store(
    transport: TelegramFailoverSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for route in transport.routes:
        monkeypatch.setattr(route, "close", AsyncMock())
    await transport.close()
    for route in transport.routes:
        cast("AsyncMock", route.close).assert_awaited_once()
    cast("Mock", transport.runtime_status).close.assert_not_awaited()
