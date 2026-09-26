import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Self

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatType
from aiogram.filters import CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import Message
from dishka import AsyncContainer
from dishka.integrations.aiogram import FromDishka, inject, setup_dishka

from core.telegram.exceptions import (
    TelegramAccessError,
    TelegramInvitationError,
    TelegramLimitError,
    TelegramServiceError,
)
from core.telegram.schemas import InvitationToken, TelegramParticipant
from core.telegram.storages import TelegramTransaction
from core.telegram.use_cases import TelegramUseCase


@inject
async def handle_start(
    message: Message,
    command: CommandObject,
    use_case: FromDishka[TelegramUseCase],
    transaction: FromDishka[TelegramTransaction],
    current_datetime: FromDishka[datetime],
) -> None:
    if message.from_user is None:
        return
    value = command.args
    if value is None or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) is None:
        await message.answer("Open a valid invitation link to request access.")
        return
    try:
        await use_case.request_connection(
            token=InvitationToken(value),
            participant=TelegramParticipant(
                user_id=message.from_user.id,
                private_chat_id=message.chat.id,
                first_name=message.from_user.first_name,
                username=message.from_user.username or "",
            ),
            now=current_datetime,
        )
        await transaction.commit()
    except TelegramInvitationError, TelegramAccessError, TelegramLimitError:
        await transaction.rollback()
        await message.answer("This invitation is unavailable. Ask for a new link.")
    except TelegramServiceError:
        await transaction.rollback()
        await message.answer("Connection service is temporarily unavailable. Try again later.")
    else:
        await message.answer("Request sent. The Workspace owner must approve your connection.")


@dataclass(kw_only=True, slots=True)
class TelegramBotDispatcher:
    bot: Bot
    dispatcher: Dispatcher

    @classmethod
    def create(cls, *, container: AsyncContainer, bot: Bot) -> Self:
        router = Router(name="telegram_connections")
        router.message.register(handle_start, CommandStart(), F.chat.type == ChatType.PRIVATE)
        dispatcher = Dispatcher(disable_fsm=True)
        dispatcher.include_router(router)
        setup_dishka(container=container, router=dispatcher)
        return cls(bot=bot, dispatcher=dispatcher)

    async def feed_raw_update(self, update: dict[str, Any]) -> None:
        await self.dispatcher.feed_raw_update(bot=self.bot, update=update)

    async def close(self) -> None:
        await self.bot.session.close()
