import asyncio
from dataclasses import dataclass
from time import monotonic

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import SetChatMenuButton, SetMyCommands
from aiogram.methods.base import TelegramMethod
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, MenuButtonCommands

from infra.config.constants import constants
from infra.config.loggers import log_sanitized_exception
from infra.telegram.bot import TelegramFailoverSession

COMMANDS = (
    ("start", "Начать работу и открыть меню", "Start and open the menu"),
    ("menu", "Открыть главное меню", "Open the main menu"),
    ("finance", "Добавить или продолжить операцию", "Add or resume a transaction"),
    ("help", "Как пользоваться ботом", "How to use the bot"),
    ("cancel", "Отменить текущую операцию", "Cancel the current transaction"),
)


@dataclass(kw_only=True, slots=True)
class TelegramCommandMenu:
    bot: Bot
    transport: TelegramFailoverSession
    registered: bool
    next_attempt_at: float

    async def send(self, index: int, method: TelegramMethod[bool]) -> None:
        accepted = await self.transport.request_route(
            bot=self.bot,
            method=method,
            index=index,
            request_timeout=constants.telegram.connection_timeout_seconds,
        )
        if not accepted:
            msg = "Telegram command menu registration was not accepted"
            raise RuntimeError(msg)

    async def configure(self, index: int) -> None:
        if self.registered or monotonic() < self.next_attempt_at:
            return
        try:
            async with asyncio.timeout(constants.telegram.connection_timeout_seconds):
                for language_code in ("", "ru", "en"):
                    await self.send(
                        index,
                        SetMyCommands(
                            commands=[
                                BotCommand(
                                    command=command,
                                    description=ru if language_code == "ru" else en,
                                )
                                for command, ru, en in COMMANDS
                            ],
                            scope=BotCommandScopeAllPrivateChats(),
                            language_code=language_code,
                        ),
                    )
                await self.send(
                    index,
                    SetChatMenuButton(menu_button=MenuButtonCommands()),
                )
        except Exception as exc:  # noqa: BLE001
            delay = (
                exc.retry_after
                if isinstance(exc, TelegramRetryAfter)
                else constants.telegram.connection_retry_seconds
            )
            self.next_attempt_at = monotonic() + delay
            log_sanitized_exception(event="Telegram command menu registration failed", error=exc)
        else:
            self.registered = True
