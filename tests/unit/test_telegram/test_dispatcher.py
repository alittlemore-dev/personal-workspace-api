from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from aiogram import Bot
from aiogram.methods import SendMessage
from dishka import Provider, Scope, make_async_container, provide

from core.telegram.exceptions import TelegramLimitError
from core.telegram.schemas import TelegramParticipant
from core.telegram.storages import TelegramTransaction
from core.telegram.use_cases import TelegramUseCase
from entrypoints.telegram.dispatcher import TelegramBotDispatcher
from tests.unit.mocks.providers.telegram import MockTelegramProvider

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
INVITE_PAYLOAD = "invite"


class TelegramNowProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def provide_now(self) -> datetime:
        return NOW


def update(*, chat_type: str, text: str) -> dict[str, object]:
    return {
        "update_id": 7,
        "message": {
            "message_id": 11,
            "date": int(NOW.timestamp()),
            "chat": {"id": 42, "type": chat_type},
            "from": {"id": 42, "is_bot": False, "first_name": "Boris", "username": "boris"},
            "text": text,
        },
    }


@pytest.mark.asyncio
async def test_private_start_requests_pending_connection_and_replies() -> None:
    container = make_async_container(MockTelegramProvider(), TelegramNowProvider())
    use_case = await container.get(TelegramUseCase)
    transaction = await container.get(TelegramTransaction)
    bot = Bot("123456:TEST_TOKEN")
    dispatcher = TelegramBotDispatcher.create(container=container, bot=bot)
    try:
        with patch.object(Bot, "__call__", new_callable=AsyncMock) as send:
            await dispatcher.feed_raw_update(
                update(chat_type="private", text=f"/start {INVITE_PAYLOAD}"),
            )
        cast("AsyncMock", use_case.request_connection).assert_awaited_once_with(
            token=INVITE_PAYLOAD,
            participant=TelegramParticipant(
                user_id=42,
                private_chat_id=42,
                first_name="Boris",
                username="boris",
            ),
            now=NOW,
        )
        cast("AsyncMock", transaction.commit).assert_awaited_once_with()
        assert isinstance(send.call_args.args[0], SendMessage)
        assert send.call_args.args[0].chat_id == 42
    finally:
        await dispatcher.close()
        await container.close()


@pytest.mark.asyncio
async def test_group_start_cannot_redeem_invitation() -> None:
    container = make_async_container(MockTelegramProvider(), TelegramNowProvider())
    use_case = await container.get(TelegramUseCase)
    transaction = await container.get(TelegramTransaction)
    bot = Bot("123456:TEST_TOKEN")
    dispatcher = TelegramBotDispatcher.create(container=container, bot=bot)
    try:
        with patch.object(Bot, "__call__", new_callable=AsyncMock) as send:
            await dispatcher.feed_raw_update(update(chat_type="group", text="/start invite"))
        cast("AsyncMock", use_case.request_connection).assert_not_awaited()
        cast("AsyncMock", transaction.commit).assert_not_awaited()
        send.assert_not_awaited()
    finally:
        await dispatcher.close()
        await container.close()


@pytest.mark.asyncio
async def test_capacity_limit_gets_neutral_reply() -> None:
    container = make_async_container(MockTelegramProvider(), TelegramNowProvider())
    use_case = await container.get(TelegramUseCase)
    transaction = await container.get(TelegramTransaction)
    cast("AsyncMock", use_case.request_connection).side_effect = TelegramLimitError
    bot = Bot("123456:TEST_TOKEN")
    dispatcher = TelegramBotDispatcher.create(container=container, bot=bot)
    try:
        with patch.object(Bot, "__call__", new_callable=AsyncMock) as send:
            await dispatcher.feed_raw_update(update(chat_type="private", text="/start invite"))
        assert send.await_count == 1
        cast("AsyncMock", transaction.rollback).assert_awaited_once_with()
        cast("AsyncMock", transaction.commit).assert_not_awaited()
        assert isinstance(send.call_args.args[0], SendMessage)
    finally:
        await dispatcher.close()
        await container.close()
