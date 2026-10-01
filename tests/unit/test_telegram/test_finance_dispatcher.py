from collections.abc import AsyncGenerator
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramNotFound,
    TelegramUnauthorizedError,
)
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.methods.base import TelegramMethod, TelegramType
from aiogram.types import InlineKeyboardMarkup
from dishka import Provider, Scope, make_async_container, provide

from core.finance.enums import FinanceKind, FinanceSource
from core.finance.exceptions import FinanceConflictError, FinanceNotFoundError
from core.finance.use_cases import FinanceUseCase
from core.i18n.enums import LanguageEnum
from core.notifications.clients import PermanentReminderSendError, RetryableReminderSendError
from core.telegram.enums import TelegramConnectionState
from core.telegram.exceptions import TelegramAccessError, TelegramServiceError
from core.telegram.schemas import TelegramConnection
from core.telegram.storages import TelegramTransaction
from entrypoints.telegram.dispatcher import TelegramBotDispatcher
from infra.telegram.reminder_sender import AiogramReminderSender
from tests.helpers.factory import FactoryHelper
from tests.unit.mocks.providers.finance import MockFinanceProvider
from tests.unit.mocks.providers.telegram import MockTelegramProvider
from tests.unit.test_telegram.test_dispatcher import NOW


class FinanceBotApiSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[SendMessage] = []

    async def close(self) -> None:
        pass

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,  # noqa: ASYNC109
    ) -> TelegramType:
        _ = (bot, timeout)
        if isinstance(method, SendMessage):
            self.calls.append(method)
        return cast("TelegramType", True)

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,  # noqa: ASYNC109
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes]:
        _ = (url, headers, timeout, chunk_size, raise_for_status)
        yield b""


class FinanceBotTimeProvider(Provider):
    def __init__(self, now: datetime) -> None:
        super().__init__()
        self.now = now

    @provide(scope=Scope.REQUEST)
    def provide_now(self) -> datetime:
        return self.now


class FinanceBotHarness:
    async def start(self) -> None:
        self.time_provider = FinanceBotTimeProvider(now=NOW)
        self.container = make_async_container(
            MockFinanceProvider(),
            MockTelegramProvider(),
            self.time_provider,
        )
        self.use_case = cast("Mock", await self.container.get(FinanceUseCase))
        self.transaction = cast("Mock", await self.container.get(TelegramTransaction))
        self.connection = TelegramConnection(
            id="c" * 32,
            owner_username="owner",
            telegram_user_id=42,
            private_chat_id=42,
            label="Family",
            first_name="Boris",
            username="boris",
            state=TelegramConnectionState.ACTIVE,
            requested_at=NOW,
            connected_at=NOW,
            last_contact_at=NOW,
            notify_birthday=False,
            notify_memorable_date=False,
            notify_finance_transaction=False,
            notify_finance_limit=False,
            language=LanguageEnum.EN,
        )
        factory = FactoryHelper()
        self.month = factory.core.finance_month(
            categories=[
                factory.core.finance_category(category_id=f"{i:032x}", name=f"Category {i}")
                for i in range(10)
            ],
        )
        self.use_case.telegram_context.return_value = (self.connection, self.month)
        self.use_case.confirmed_telegram_operation.return_value = None
        self.use_case.create_transaction.return_value = factory.core.finance_transaction()
        self.storage = MemoryStorage()
        self.session = FinanceBotApiSession()
        self.bot = Bot("123456:TEST_TOKEN", session=self.session)
        self.dispatcher = TelegramBotDispatcher.create(
            container=self.container,
            bot=self.bot,
            storage=self.storage,
            isolation=SimpleEventIsolation(),
        )
        self.calls = self.session.calls
        self.sequence = 0

    async def close(self) -> None:
        await self.dispatcher.close()
        await self.container.close()

    async def feed(self, text: str = "", callback: str = "", chat_type: str = "private") -> None:
        self.sequence += 1
        message = {
            "message_id": self.sequence,
            "date": int(NOW.timestamp()),
            "chat": {"id": 42, "type": chat_type},
            "from": {"id": 42, "is_bot": False, "first_name": "Boris"},
            "text": text,
        }
        update: dict[str, object] = {"update_id": self.sequence}
        if callback:
            update["callback_query"] = {
                "id": str(self.sequence),
                "from": message["from"],
                "chat_instance": "chat",
                "data": callback,
                "message": message,
            }
        else:
            update["message"] = message

        await self.dispatcher.feed_raw_update(update)

    def button(self, action: str) -> str:
        keyboard = self.calls[-1].reply_markup
        assert isinstance(keyboard, InlineKeyboardMarkup)
        return next(
            b.callback_data
            for row in keyboard.inline_keyboard
            for b in row
            if b.callback_data and b.callback_data.endswith(f":{action}")
        )

    async def choose(self, action: str) -> None:
        await self.feed(callback=self.button(action))

    async def complete(self) -> str:
        await self.feed("/finance")
        await self.choose("expense")
        await self.choose("cat_0")
        await self.feed("12,50")
        await self.choose("USD")
        await self.choose("now")
        await self.choose("skip")
        return self.button("confirm")


@pytest_asyncio.fixture
async def harness() -> AsyncGenerator[FinanceBotHarness]:
    harness = FinanceBotHarness()
    await harness.start()
    try:
        yield harness
    finally:
        await harness.close()


async def test_guided_expense_confirms_with_trusted_actor_and_commit(
    harness: FinanceBotHarness,
) -> None:
    confirmation = await harness.complete()
    harness.use_case.create_transaction.assert_not_awaited()
    await harness.feed(callback=confirmation)
    params = harness.use_case.create_transaction.call_args.args[0]
    assert params.owner_username == "owner"
    assert params.actor.source == FinanceSource.TELEGRAM
    assert params.actor.identifier == "42"
    assert params.actor.label == "Family"
    assert params.actor.month_id == harness.month.id
    assert str(params.draft.amount) == "12.50"
    assert params.draft.description == ""
    assert harness.calls[-1].text == "Transaction saved."
    harness.use_case.confirmed_telegram_operation.return_value = (
        harness.use_case.create_transaction.return_value
    )
    await harness.feed(callback=confirmation)
    harness.use_case.create_transaction.assert_awaited_once()


async def test_retry_recovers_confirmed_transaction_after_valkey_loss(
    harness: FinanceBotHarness,
) -> None:
    confirmation = await harness.complete()
    harness.use_case.confirmed_telegram_operation.return_value = (
        FactoryHelper().core.finance_transaction()
    )
    await harness.storage.close()
    harness.storage.storage.clear()
    await harness.feed(callback=confirmation)
    assert harness.calls[-1].text == "Transaction saved."
    harness.use_case.create_transaction.assert_not_awaited()


async def test_group_cannot_start_or_confirm(harness: FinanceBotHarness) -> None:
    await harness.feed("/finance", chat_type="group")
    await harness.feed(callback=f"fin:{'a' * 32}:1:confirm", chat_type="group")
    harness.use_case.telegram_context.assert_not_awaited()
    assert not harness.calls


@pytest.mark.parametrize("error", [TelegramAccessError, FinanceNotFoundError])
async def test_unavailable_access_or_tracker_cannot_create(
    harness: FinanceBotHarness,
    error: type[Exception],
) -> None:
    harness.use_case.telegram_context.side_effect = error
    await harness.feed("/finance")
    harness.use_case.create_transaction.assert_not_awaited()
    assert harness.calls


async def test_old_buttons_and_expired_forms_cannot_change_input(
    harness: FinanceBotHarness,
) -> None:
    await harness.feed("/finance")
    old = harness.button("expense")
    await harness.choose("expense")
    await harness.feed(callback=old)
    assert "expired" in harness.calls[-1].text
    key = StorageKey(
        bot_id=harness.bot.id,
        chat_id=42,
        user_id=42,
        destiny=f"owner:{harness.connection.id}",
    )
    data = await harness.storage.get_data(key)
    assert data["step"] == "category"
    data["expires_at"] = (NOW - timedelta(seconds=1)).isoformat()
    await harness.storage.set_data(key, data)
    await harness.feed("anything")
    assert await harness.storage.get_data(key) == {}
    harness.use_case.create_transaction.assert_not_awaited()


async def test_pagination_uses_short_callbacks_and_cancel_clears_state(
    harness: FinanceBotHarness,
) -> None:
    await harness.feed("/start")
    await harness.choose("expense")
    keyboard = harness.calls[-1].reply_markup
    assert isinstance(keyboard, InlineKeyboardMarkup)
    assert all(
        b.callback_data is not None and len(b.callback_data.encode()) <= 64
        for row in keyboard.inline_keyboard
        for b in row
    )
    await harness.choose("page_1")
    assert "Category 8" in str(harness.calls[-1].reply_markup)
    await harness.choose("cancel")
    assert harness.calls[-1].text == "Transaction entry canceled."
    harness.use_case.create_transaction.assert_not_awaited()


async def test_fractional_amd_and_bad_amount_are_rejected_without_losing_draft(
    harness: FinanceBotHarness,
) -> None:
    await harness.feed("/finance")
    await harness.choose("expense")
    await harness.choose("cat_0")
    await harness.feed("NaN")
    assert "Check" in harness.calls[-1].text
    await harness.feed("12,50")
    amd = harness.button("AMD")
    await harness.feed(callback=amd)
    assert "Check" in harness.calls[-1].text
    await harness.feed(callback=amd.replace(":AMD", ":USD"))
    assert "transaction time" in harness.calls[-1].text


async def test_revocation_and_month_change_invalidate_open_confirmation(
    harness: FinanceBotHarness,
) -> None:
    confirmation = await harness.complete()
    harness.use_case.telegram_context.side_effect = TelegramAccessError
    await harness.feed(callback=confirmation)
    harness.use_case.create_transaction.assert_not_awaited()
    harness.use_case.telegram_context.side_effect = None
    harness.use_case.telegram_context.return_value = (
        harness.connection,
        replace(harness.month, id="next-month"),
    )
    await harness.feed(callback=confirmation)
    assert "expired" in harness.calls[-1].text
    harness.use_case.create_transaction.assert_not_awaited()


async def test_failed_commit_keeps_confirmation_for_retry(harness: FinanceBotHarness) -> None:
    confirmation = await harness.complete()
    # context commit, receipt-read commit, then business commit
    harness.transaction.commit.side_effect = [None, None, TelegramServiceError()]
    await harness.feed(callback=confirmation)
    assert "Retry" in harness.calls[-1].text
    harness.transaction.rollback.assert_awaited()


async def test_archived_category_rejection_clears_draft(harness: FinanceBotHarness) -> None:
    confirmation = await harness.complete()
    harness.use_case.create_transaction.side_effect = FinanceConflictError
    await harness.feed(callback=confirmation)
    assert "expired" in harness.calls[-1].text


async def test_russian_income_custom_datetime_and_back(harness: FinanceBotHarness) -> None:
    factory = FactoryHelper()
    month = replace(
        harness.month,
        categories=[factory.core.finance_category(kind=FinanceKind.INCOME)],
    )
    harness.use_case.telegram_context.return_value = (
        replace(harness.connection, language=LanguageEnum.RU),
        month,
    )
    await harness.feed("/finance")
    await harness.choose("income")
    await harness.choose("cat_0")
    await harness.feed("100")
    await harness.choose("EUR")
    await harness.choose("custom")
    await harness.feed("26.08.2026 12:00")
    assert "Проверьте" in harness.calls[-1].text
    await harness.feed("26.09.2026 12:00")
    await harness.feed("Зарплата")
    await harness.choose("back")
    await harness.feed("Премия")
    await harness.choose("confirm")
    assert harness.calls[-1].text == "Операция сохранена."
    assert harness.use_case.create_transaction.call_args.args[0].draft.description == "Премия"


async def test_category_deleted_during_description_invalidates_form(
    harness: FinanceBotHarness,
) -> None:
    await harness.feed("/finance")
    await harness.choose("expense")
    await harness.choose("cat_0")
    await harness.feed("10")
    await harness.choose("USD")
    await harness.choose("now")
    harness.use_case.telegram_context.return_value = (
        harness.connection,
        replace(harness.month, categories=[]),
    )
    await harness.feed("Groceries")
    assert "expired" in harness.calls[-1].text
    key = StorageKey(
        bot_id=harness.bot.id,
        chat_id=42,
        user_id=42,
        destiny=f"owner:{harness.connection.id}",
    )
    assert await harness.storage.get_data(key) == {}


async def test_uninitialized_tracker_instruction_uses_connection_language(
    harness: FinanceBotHarness,
) -> None:
    harness.use_case.telegram_context.return_value = (
        replace(harness.connection, language=LanguageEnum.RU),
        None,
    )
    await harness.feed("/finance")
    assert "сайте" in harness.calls[-1].text
    harness.use_case.create_transaction.assert_not_awaited()


@pytest.mark.parametrize(
    ("month_number", "invalid_time"),
    [(3, "08.03.2026 02:30"), (11, "01.11.2026 01:30")],
)
async def test_dst_gaps_and_ambiguous_times_keep_date_step(
    harness: FinanceBotHarness,
    month_number: int,
    invalid_time: str,
) -> None:
    harness.time_provider.now = datetime(2026, month_number, 15, 12, tzinfo=UTC)
    month = replace(
        harness.month,
        period_start=date(2026, month_number, 1),
        time_zone=ZoneInfo("America/New_York"),
    )
    harness.use_case.telegram_context.return_value = (harness.connection, month)
    await harness.feed("/finance")
    await harness.choose("expense")
    await harness.choose("cat_0")
    await harness.feed("10")
    await harness.choose("USD")
    await harness.choose("custom")
    await harness.feed(invalid_time)
    assert "Check" in harness.calls[-1].text
    await harness.feed(f"15.{month_number:02d}.2026 12:00")
    assert "description" in harness.calls[-1].text
    harness.use_case.create_transaction.assert_not_awaited()


@pytest.mark.parametrize(
    ("error_type", "expected"),
    [
        (TelegramForbiddenError, PermanentReminderSendError),
        (TelegramBadRequest, PermanentReminderSendError),
        (TelegramUnauthorizedError, PermanentReminderSendError),
        (TelegramNotFound, PermanentReminderSendError),
        (TelegramNetworkError, RetryableReminderSendError),
    ],
)
async def test_notification_sender_classifies_bot_api_failures(
    harness: FinanceBotHarness,
    error_type: type[TelegramAPIError],
    expected: type[Exception],
) -> None:
    error = error_type(
        method=cast("Any", SendMessage(chat_id=42, text="Financial notification")),
        message="Fake API failure",
    )
    with patch.object(harness.session, "make_request", side_effect=error), pytest.raises(expected):
        await AiogramReminderSender(bot=harness.bot).send(
            private_chat_id=42,
            text="Financial notification",
        )


async def test_callback_ack_delay_across_month_boundary_invalidates_form(
    harness: FinanceBotHarness,
) -> None:
    harness.time_provider.now = datetime(2026, 9, 30, 23, 59, 59, tzinfo=UTC)
    confirmation = await harness.complete()
    elapsed = [0.0]
    original_request = harness.session.make_request

    async def request(
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,  # noqa: ASYNC109 -- Matches the aiogram session API.
    ) -> TelegramType:
        if isinstance(method, AnswerCallbackQuery):
            elapsed[0] = 2
        return await original_request(bot, method, timeout)

    with (
        patch("entrypoints.telegram.finance.monotonic", side_effect=lambda: elapsed[0]),
        patch.object(harness.session, "make_request", side_effect=request),
    ):
        await harness.feed(callback=confirmation)
    assert "expired" in harness.calls[-1].text
    harness.use_case.create_transaction.assert_not_awaited()
