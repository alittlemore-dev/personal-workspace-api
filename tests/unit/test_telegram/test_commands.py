import asyncio
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import SetChatMenuButton, SetMyCommands
from aiogram.types import BotCommandScopeAllPrivateChats, MenuButtonCommands

from infra.config.constants import constants
from infra.telegram.bot import TelegramFailoverSession
from infra.telegram.commands import TelegramCommandMenu


@pytest.fixture
def command_menu() -> TelegramCommandMenu:
    transport = Mock(spec=TelegramFailoverSession)
    transport.request_route = AsyncMock(return_value=True)
    return TelegramCommandMenu(
        bot=Bot("123456:TEST_TOKEN"),
        transport=transport,
        registered=False,
        next_attempt_at=0,
    )


async def test_registers_localized_private_commands_and_menu_once(
    command_menu: TelegramCommandMenu,
) -> None:
    await command_menu.configure(1)
    await command_menu.configure(0)
    calls = cast("Mock", command_menu.transport).request_route.await_args_list
    assert len(calls) == 4
    for call, language in zip(calls[:3], ("", "ru", "en"), strict=True):
        method = call.kwargs["method"]
        assert isinstance(method, SetMyCommands)
        assert method.language_code == language
        assert isinstance(method.scope, BotCommandScopeAllPrivateChats)
        assert [command.command for command in method.commands] == [
            "start",
            "menu",
            "finance",
            "help",
            "cancel",
        ]
        assert method.commands[0].description == (
            "Начать работу и открыть меню" if language == "ru" else "Start and open the menu"
        )
        assert call.kwargs["index"] == 1
    method = calls[-1].kwargs["method"]
    assert isinstance(method, SetChatMenuButton)
    assert isinstance(method.menu_button, MenuButtonCommands)
    assert command_menu.registered


@pytest.mark.parametrize("failure", ["network", "rate_limit", "rejected", "timeout"])
async def test_optional_registration_retries_without_failing_delivery_or_exposing_secrets(
    command_menu: TelegramCommandMenu,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: str,
) -> None:
    clock = [100.0]
    monkeypatch.setattr("infra.telegram.commands.monotonic", lambda: clock[0])
    request = cast("Mock", command_menu.transport).request_route
    failures = {
        "network": TelegramNetworkError(method=SetMyCommands(commands=[]), message="PRIVATE_TOKEN"),
        "rate_limit": TelegramRetryAfter(
            method=SetMyCommands(commands=[]),
            message="PRIVATE_TOKEN",
            retry_after=120,
        ),
        "rejected": False,
        "timeout": TimeoutError("PRIVATE_TOKEN"),
    }
    request.side_effect = [failures[failure], True, True, True, True]
    await command_menu.configure(0)
    assert not command_menu.registered
    delay = 120 if failure == "rate_limit" else constants.telegram.connection_retry_seconds
    assert command_menu.next_attempt_at == 100 + delay
    await command_menu.configure(0)
    assert request.await_count == 1
    clock[0] = command_menu.next_attempt_at
    await command_menu.configure(1)
    assert command_menu.registered
    assert request.await_count == 5
    log = capsys.readouterr().out
    assert "Telegram command menu registration failed" in log
    assert "PRIVATE_TOKEN" not in log


async def test_shutdown_cancels_registration(command_menu: TelegramCommandMenu) -> None:
    cast("Mock", command_menu.transport).request_route.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await command_menu.configure(0)
    assert not command_menu.registered
