import asyncio
import base64
import json
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiogram.client.telegram import TelegramAPIServer
from aiogram.exceptions import TelegramNetworkError
from dishka import AsyncContainer

from core.telegram.enums import TelegramRuntimeStatus
from entrypoints.litestar.initializers.main import create_litestar_app
from infra.config.settings import SecretStrExtended, TelegramSettings, settings
from infra.ioc.prodivers.notifications_provider import NotificationsProvider
from infra.telegram.bot import create_telegram_bot
from infra.telegram.reminder_sender import AiogramReminderSender
from infra.telegram.runtime import TelegramBotRuntime, TelegramRuntimeState
from infra.valkey.telegram_runtime import TelegramRuntimeStatusStore


@pytest.mark.parametrize("protocol", ["socks5", "http", "direct"])
@pytest.mark.asyncio
async def test_bot_routes_api_calls_and_decodes_proxy_credentials(protocol: str) -> None:  # noqa: PLR0915
    destinations: list[str] = []
    authorizations: list[tuple[str, str]] = []
    methods: list[str] = []
    errors: list[Exception] = []

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            if protocol == "socks5":
                version, method_count = await reader.readexactly(2)
                offered = await reader.readexactly(method_count)
                assert version == 5
                assert 2 in offered
                writer.write(b"\x05\x02")
                await writer.drain()
                auth_version, user_length = await reader.readexactly(2)
                username = await reader.readexactly(user_length)
                password_length = (await reader.readexactly(1))[0]
                password = await reader.readexactly(password_length)
                assert auth_version == 1
                authorizations.append((username.decode(), password.decode()))
                writer.write(b"\x01\x00")
                await writer.drain()
                version, command, reserved, address_type = await reader.readexactly(4)
                assert (version, command, reserved, address_type) == (5, 1, 0, 3)
                host_length = (await reader.readexactly(1))[0]
                host = await reader.readexactly(host_length)
                port = int.from_bytes(await reader.readexactly(2), "big")
                destinations.append(f"{host.decode()}:{port}")
                writer.write(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
                await writer.drain()
            elif protocol == "http":
                connect = (await reader.readuntil(b"\r\n\r\n")).decode()
                destinations.append(connect.split(" ")[1])
                auth = next(
                    line.split("Basic ")[1]
                    for line in connect.split("\r\n")
                    if line.lower().startswith("proxy-authorization:")
                )
                auth_username, auth_password = base64.b64decode(auth).decode().split(":", 1)
                authorizations.append((auth_username, auth_password))
                writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
                await writer.drain()

            request = (await reader.readuntil(b"\r\n\r\n")).decode()
            method = request.split(" ")[1].rsplit("/", 1)[1]
            methods.append(method)
            headers = dict(
                line.split(": ", 1) for line in request.split("\r\n")[1:] if ": " in line
            )
            await reader.readexactly(int(headers.get("Content-Length", "0")))
            results: dict[str, object] = {
                "getMe": {"id": 123456, "is_bot": True, "first_name": "Test"},
                "setWebhook": True,
                "sendMessage": {
                    "message_id": 1,
                    "date": 1,
                    "chat": {"id": 123, "type": "private"},
                    "text": "Test",
                },
            }
            body = json.dumps({"ok": True, "result": results[method]}).encode()
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
                + body,
            )
            await writer.drain()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    proxy_url = (
        "" if protocol == "direct" else f"{protocol}://test%40user:pass%3Aword@127.0.0.1:{port}"
    )
    config = TelegramSettings(
        _env_file=None,
        proxy_urls=[SecretStrExtended(proxy_url)] if proxy_url else [],
        bot_token=SecretStrExtended("123456:TEST_TOKEN"),
    )
    store = Mock(spec=TelegramRuntimeStatusStore)
    store.get_ready_route = AsyncMock(return_value=0)
    bot = create_telegram_bot(telegram_settings=config, runtime_status=store)
    target = f"http://127.0.0.1:{port}" if protocol == "direct" else "http://telegram.test:8080"
    bot.session.api = TelegramAPIServer.from_base(target)
    try:
        assert (await asyncio.wait_for(bot.get_me(), timeout=2)).id == 123456
        assert await asyncio.wait_for(bot.set_webhook(url="https://app.test/webhook"), timeout=2)
        await asyncio.wait_for(
            AiogramReminderSender(bot=bot).send(private_chat_id=123, text="Test"),
            timeout=2,
        )
    finally:
        await bot.session.close()
        server.close()
        await server.wait_closed()
    assert errors == []
    assert methods == ["getMe", "setWebhook", "sendMessage"]
    if protocol == "direct":
        assert destinations == []
    else:
        assert destinations == ["telegram.test:8080"] * 3
        assert authorizations == [("test@user", "pass:word")] * 3


@pytest.mark.asyncio
async def test_proxy_failure_does_not_fall_back_to_direct_requests() -> None:
    direct_calls: list[bool] = []

    def direct_connection(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        direct_calls.append(True)
        writer.close()

    direct_server = await asyncio.start_server(direct_connection, "127.0.0.1", 0)
    direct_port = direct_server.sockets[0].getsockname()[1]
    server = await asyncio.start_server(lambda _reader, writer: writer.close(), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    store = Mock(spec=TelegramRuntimeStatusStore)
    store.get_ready_route = AsyncMock(return_value=0)
    store.mark_failed = AsyncMock(return_value=True)
    bot = create_telegram_bot(
        runtime_status=store,
        telegram_settings=TelegramSettings(
            _env_file=None,
            proxy_urls=[SecretStrExtended(f"http://127.0.0.1:{port}")],
            bot_token=SecretStrExtended("123456:TEST_TOKEN"),
        ),
    )
    bot.session.api = TelegramAPIServer.from_base(f"http://127.0.0.1:{direct_port}")
    try:
        with pytest.raises(TelegramNetworkError):
            await asyncio.wait_for(bot.get_me(), timeout=2)
    finally:
        await bot.session.close()
        server.close()
        await server.wait_closed()
        direct_server.close()
        await direct_server.wait_closed()
    assert direct_calls == []


@pytest.mark.asyncio
async def test_web_and_worker_use_same_configured_client_and_close_it(
    container: AsyncContainer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings.telegram, "available", True)
    monkeypatch.setattr(
        settings.telegram,
        "proxy_urls",
        [SecretStrExtended("socks5://proxy.test:1080")],
    )
    bot = Mock()
    bot.session.close = AsyncMock()
    with patch(
        "entrypoints.litestar.initializers.main.create_telegram_bot",
        return_value=bot,
    ) as factory:
        app = create_litestar_app(
            lifespan=[],
            container=container,
            extra_plugins=[],
            extra_middlewares=[],
        )
    factory.assert_called_once_with(
        telegram_settings=settings.telegram,
        runtime_status=app.state.telegram_runtime_status,
    )
    await app.state.telegram_dispatcher.close()
    bot.session.close.assert_awaited_once()
    bot.session.close.reset_mock()

    provider = NotificationsProvider()
    store = Mock(spec=TelegramRuntimeStatusStore)
    with patch(
        "infra.ioc.prodivers.notifications_provider.create_telegram_bot",
        return_value=bot,
    ) as factory:
        iterator = cast("Any", provider.provide_sender)(runtime_status=store)
        assert isinstance(await anext(iterator), AiogramReminderSender)
        factory.assert_called_once_with(telegram_settings=settings.telegram, runtime_status=store)
        await iterator.aclose()
    bot.session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_real_proxy_pool_fails_over_stays_sticky_and_never_replays_send(  # noqa: PLR0915
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary_up = False
    backup_up = True
    uncertain_send = False
    clock = [0.0]
    monkeypatch.setattr("infra.telegram.bot.monotonic", lambda: clock[0])
    calls: list[tuple[int, str]] = []

    async def handle(
        index: int,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            if not (primary_up if index == 0 else backup_up):
                return
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            await writer.drain()
            request = (await reader.readuntil(b"\r\n\r\n")).decode()
            method = request.split(" ")[1].rsplit("/", 1)[1]
            calls.append((index, method))
            headers = dict(
                line.split(": ", 1) for line in request.split("\r\n")[1:] if ": " in line
            )
            await reader.readexactly(int(headers.get("Content-Length", "0")))
            if method == "sendMessage" and uncertain_send:
                return
            results: dict[str, object] = {
                "getMe": {"id": 123456, "is_bot": True, "first_name": "Test"},
                "setWebhook": True,
            }
            body = json.dumps({"ok": True, "result": results[method]}).encode()
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
                + body,
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    primary = await asyncio.start_server(lambda r, w: handle(0, r, w), "127.0.0.1", 0)
    backup = await asyncio.start_server(lambda r, w: handle(1, r, w), "127.0.0.1", 0)
    urls = [
        f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}" for server in (primary, backup)
    ]
    config = settings.telegram.model_copy(
        update={
            "proxy_urls": [SecretStrExtended(url) for url in urls],
            "bot_token": SecretStrExtended("123456:TEST_TOKEN"),
        },
    )
    store = Mock(spec=TelegramRuntimeStatusStore)
    store.get_ready_route = AsyncMock(return_value=1)
    store.mark_failed = AsyncMock(return_value=True)
    bot = create_telegram_bot(telegram_settings=config, runtime_status=store)
    bot.session.api = TelegramAPIServer.from_base("http://telegram.test:8080")
    runtime = TelegramBotRuntime(
        bot=bot,
        state=TelegramRuntimeState(status=TelegramRuntimeStatus.CONNECTING),
        status_store=store,
    )
    try:
        assert await asyncio.wait_for(runtime.connect(None, None), timeout=2) == 1
        assert calls == [(1, "getMe"), (1, "setWebhook")]
        primary_up = True
        clock[0] = 31
        assert await runtime.connect(1, 1) == 1
        await runtime.check_backup(1, 0)
        assert calls[-2:] == [(1, "getMe"), (0, "getMe")]
        uncertain_send = True
        with pytest.raises(TelegramNetworkError):
            await asyncio.wait_for(bot.send_message(chat_id=123, text="Test"), timeout=2)
        assert [call for call in calls if call[1] == "sendMessage"] == [(1, "sendMessage")]
        store.mark_failed.assert_awaited_with(1)
        assert await runtime.connect(1, 1) == 0
        backup_up = False
        primary_up = False
        with pytest.raises(TelegramNetworkError):
            await runtime.connect(0, 0)
        clock[0] = 62
        primary_up = True
        assert await runtime.connect(0, None) == 0
    finally:
        await bot.session.close()
        for server in (primary, backup):
            server.close()
            await server.wait_closed()
