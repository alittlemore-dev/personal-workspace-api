import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import InvalidOperation
from time import monotonic
from typing import Any
from uuid import uuid4

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import BaseEventIsolation, BaseStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)
from dishka.integrations.aiogram import FromDishka, inject

from core.finance.enums import FinanceCurrency, FinanceKind, FinanceSource
from core.finance.exceptions import (
    FinanceConflictError,
    FinanceNotFoundError,
    FinanceRateUnavailableError,
    InvalidFinanceDataError,
)
from core.finance.schemas import (
    TRANSACTION_DESCRIPTION_MAX_LENGTH,
    Amount,
    ConfirmedFinanceOperationParams,
    CreateFinanceTransactionParams,
    FinanceActor,
    FinanceMonth,
    FinanceTransactionDraft,
    TelegramFinanceContextParams,
)
from core.finance.use_cases import FinanceUseCase
from core.i18n.enums import LanguageEnum
from core.telegram.exceptions import TelegramAccessError, TelegramServiceError
from core.telegram.schemas import TelegramConnection
from core.telegram.storages import TelegramTransaction
from entrypoints.telegram.enums import FinanceConversationText, TelegramNavigationAction
from entrypoints.telegram.keyboards import conversation_key, main_keyboard, navigation_action
from infra.config.constants import constants

CATEGORY_PAGE_SIZE = 8


@dataclass(kw_only=True, slots=True)
class FinanceConversationSession:
    message: Message
    state: FSMContext
    connection: TelegramConnection
    month: FinanceMonth
    use_case: FinanceUseCase
    transaction: TelegramTransaction
    now: datetime


@dataclass(kw_only=True, slots=True)
class FinanceConversation:
    bot: Bot
    storage: BaseStorage
    isolation: BaseEventIsolation

    async def process(
        self,
        *,
        event: Message | CallbackQuery,
        use_case: FinanceUseCase,
        transaction: TelegramTransaction,
        now: datetime,
    ) -> None:
        started = monotonic()
        message = event.message if isinstance(event, CallbackQuery) else event
        user = event.from_user
        if (
            not isinstance(message, Message)
            or user is None
            or message.chat.type != ChatType.PRIVATE
        ):
            return
        if isinstance(event, CallbackQuery):
            await event.answer()
        language = LanguageEnum.EN
        try:
            connection, month = await use_case.telegram_context(
                TelegramFinanceContextParams(
                    telegram_user_id=user.id,
                    private_chat_id=message.chat.id,
                    now=now + timedelta(seconds=monotonic() - started),
                ),
            )
            language = connection.language
            await transaction.commit()
            if month is None:
                await message.answer(
                    FinanceConversationText.INITIALIZE.get_translation(language),
                    reply_markup=main_keyboard(language),
                    parse_mode=None,
                )
                return
            key = conversation_key(self.bot.id, connection)
            async with self.isolation.lock(key=key):
                state = FSMContext(storage=self.storage, key=key)
                await self.advance(
                    event=event,
                    session=FinanceConversationSession(
                        message=message,
                        state=state,
                        connection=connection,
                        month=month,
                        use_case=use_case,
                        transaction=transaction,
                        now=now + timedelta(seconds=monotonic() - started),
                    ),
                )
        except TelegramAccessError:
            await transaction.rollback()
            await message.answer(
                FinanceConversationText.ACCESS.get_translation(language),
                reply_markup=ReplyKeyboardRemove(),
                parse_mode=None,
            )
        except FinanceNotFoundError:
            await transaction.rollback()
            await message.answer(
                FinanceConversationText.INITIALIZE.get_translation(language),
                reply_markup=main_keyboard(language),
                parse_mode=None,
            )
        except FinanceRateUnavailableError, TelegramServiceError:
            await transaction.rollback()
            await message.answer(
                FinanceConversationText.RETRY.get_translation(language),
                parse_mode=None,
            )

    def actor(
        self,
        connection: TelegramConnection,
        operation_id: str,
        month_id: str,
    ) -> FinanceActor:
        return FinanceActor(
            source=FinanceSource.TELEGRAM,
            identifier=str(connection.telegram_user_id),
            label=connection.label,
            connection_id=connection.id,
            telegram_user_id=connection.telegram_user_id,
            private_chat_id=connection.private_chat_id,
            operation_id=operation_id,
            month_id=month_id,
        )

    async def advance(
        self,
        *,
        event: Message | CallbackQuery,
        session: FinanceConversationSession,
    ) -> None:
        message, state, connection, month = (
            session.message,
            session.state,
            session.connection,
            session.month,
        )
        now = session.now
        transaction = session.transaction
        language = connection.language
        data = await state.get_data()
        callback = (
            re.fullmatch(r"fin:([a-f0-9]{32}):(\d+):([a-zA-Z0-9_-]+)", event.data or "")
            if isinstance(event, CallbackQuery)
            else None
        )
        if await self.replay(callback=callback, data=data, session=session):
            return
        month_is_current = month.period_start == now.astimezone(month.time_zone).date().replace(
            day=1,
        )
        text = message.text or ""
        is_entry = (
            isinstance(event, Message)
            and navigation_action(text) == TelegramNavigationAction.FINANCE
        )
        is_current_draft = (
            month_is_current
            and bool(data)
            and data.get("month_id") == month.id
            and datetime.fromisoformat(data["expires_at"]) > now
        )
        if month_is_current and is_entry and not is_current_draft:
            if data:
                await state.clear()
                await message.answer(
                    FinanceConversationText.STALE.get_translation(language),
                    reply_markup=main_keyboard(language),
                    parse_mode=None,
                )
            data = {
                "id": uuid4().hex,
                "revision": 0,
                "step": "kind",
                "month_id": month.id,
                "expires_at": (
                    now + timedelta(seconds=constants.finance.draft_ttl_seconds)
                ).isoformat(),
                "page": 0,
                "category_ids": [
                    c.id for c in sorted(month.categories, key=lambda c: (c.position, c.id))
                ],
            }
        elif not is_current_draft:
            await state.clear()
            await message.answer(
                FinanceConversationText.STALE.get_translation(language),
                reply_markup=main_keyboard(language),
                parse_mode=None,
            )
            return
        else:
            if isinstance(event, CallbackQuery):
                if await self.callback_event(callback=callback, data=data, session=session):
                    return
            elif not is_entry:
                try:
                    self.input(text=text, data=data, month=month)
                except ValueError, InvalidOperation, InvalidFinanceDataError:
                    await message.answer(
                        FinanceConversationText.INVALID.get_translation(language),
                        parse_mode=None,
                    )
                    return
            data["revision"] += 1
        if data.get("category_id"):
            try:
                month.get_category(data["category_id"]).check_accepting_transaction(None)
            except FinanceNotFoundError, FinanceConflictError:
                await transaction.rollback()
                await state.clear()
                await message.answer(
                    FinanceConversationText.STALE.get_translation(language),
                    reply_markup=main_keyboard(language),
                    parse_mode=None,
                )
                return
        await state.set_state(data["step"])
        await state.set_data(data)
        await self.show(message=message, data=data, month=month, language=language)

    async def callback_event(
        self,
        *,
        callback: re.Match[str] | None,
        data: dict[str, Any],
        session: FinanceConversationSession,
    ) -> bool:
        message, state, connection = session.message, session.state, session.connection
        transaction = session.transaction
        language = connection.language
        if callback is None or callback[1] != data["id"] or int(callback[2]) != data["revision"]:
            await message.answer(
                FinanceConversationText.STALE.get_translation(language),
                reply_markup=main_keyboard(language),
                parse_mode=None,
            )
            return True
        action = callback[3]
        if action == "cancel":
            await state.clear()
            await message.answer(
                FinanceConversationText.CANCELED.get_translation(language),
                reply_markup=main_keyboard(language),
                parse_mode=None,
            )
            return True
        if action == "back":
            data = self.back(data)
        else:
            try:
                await self.callback(action=action, data=data, session=session)
            except ValueError, IndexError, InvalidFinanceDataError:
                await message.answer(
                    FinanceConversationText.INVALID.get_translation(language),
                    parse_mode=None,
                )
                return True
            except FinanceConflictError, FinanceNotFoundError:
                await transaction.rollback()
                await state.clear()
                await message.answer(
                    FinanceConversationText.STALE.get_translation(language),
                    reply_markup=main_keyboard(language),
                    parse_mode=None,
                )
                return True
            if data["step"] == "done":
                await state.clear()
                await message.answer(
                    FinanceConversationText.SAVED.get_translation(language),
                    reply_markup=main_keyboard(language),
                    parse_mode=None,
                )
                return True
        return False

    async def replay(
        self,
        *,
        callback: re.Match[str] | None,
        data: dict[str, Any],
        session: FinanceConversationSession,
    ) -> bool:
        connection, month, use_case = session.connection, session.month, session.use_case
        transaction, now, state, message = (
            session.transaction,
            session.now,
            session.state,
            session.message,
        )
        language = connection.language
        if callback is not None and callback[3] == "confirm":
            existing = await use_case.confirmed_telegram_operation(
                ConfirmedFinanceOperationParams(
                    actor=self.actor(connection, callback[1], month.id),
                    owner_username=connection.owner_username,
                    now=now,
                ),
            )
            await transaction.commit()
            if existing is not None:
                if data.get("id") == callback[1]:
                    await state.clear()
                await message.answer(
                    FinanceConversationText.SAVED.get_translation(language),
                    reply_markup=main_keyboard(language),
                    parse_mode=None,
                )
                return True
        return False

    def back(self, data: dict[str, Any]) -> dict[str, Any]:
        steps = ["kind", "category", "amount", "currency", "date", "description", "confirmation"]
        step = "date" if data["step"] == "date_input" else data["step"]
        index = steps.index(step)
        data["step"] = steps[max(0, index - 1)]
        return data

    def input(self, *, text: str, data: dict[str, Any], month: FinanceMonth) -> None:
        if data["step"] == "amount":
            if re.fullmatch(r"\d+(?:[.,]\d{1,2})?", text.strip()) is None:
                raise ValueError
            amount = Amount(text.strip().replace(",", "."))
            amount.validate_range()
            if amount <= 0:
                raise ValueError
            data["amount"] = str(amount)
            data["step"] = "currency"
        elif data["step"] == "date_input":
            local = datetime.strptime(text.strip(), "%d.%m.%Y %H:%M")  # noqa: DTZ007
            zone = month.time_zone
            a = local.replace(tzinfo=zone, fold=0)
            b = local.replace(tzinfo=zone, fold=1)
            if (
                a.utcoffset() != b.utcoffset()
                or a.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != local
            ):
                raise ValueError
            data["occurred_at"] = a.astimezone(UTC).isoformat()
            self.draft(data).validate(period_start=month.period_start, time_zone=zone)
            data["step"] = "description"
        elif data["step"] == "description":
            if len(text) > TRANSACTION_DESCRIPTION_MAX_LENGTH:
                raise ValueError
            data["description"] = text
            data["step"] = "confirmation"
        else:
            raise ValueError

    def draft(self, data: dict[str, Any]) -> FinanceTransactionDraft:
        return FinanceTransactionDraft(
            category_id=data["category_id"],
            amount=Amount(data["amount"]),
            currency=FinanceCurrency(data["currency"]),
            occurred_at=datetime.fromisoformat(data["occurred_at"]),
            description=data.get("description", ""),
        )

    async def callback(
        self,
        *,
        action: str,
        data: dict[str, Any],
        session: FinanceConversationSession,
    ) -> None:
        connection, month = session.connection, session.month
        use_case, transaction, now = session.use_case, session.transaction, session.now
        step = data["step"]
        if step == "kind" and action in ("income", "expense"):
            data.update(kind=action, step="category", page=0)
        elif step == "category" and action.startswith("page_"):
            page = int(action[5:])
            count = len([c for c in month.categories if c.kind == data["kind"] and not c.archived])
            if page < 0 or page * CATEGORY_PAGE_SIZE >= count:
                raise ValueError
            data["page"] = page
        elif step == "category":
            category = month.get_category(data["category_ids"][int(action.removeprefix("cat_"))])
            if category.archived or category.kind != data["kind"]:
                raise FinanceConflictError
            data.update(category_id=category.id, step="amount")
        elif step == "currency":
            currency = FinanceCurrency(action)
            currency.validate_money(Amount(data["amount"]), positive=True)
            data.update(currency=currency.value, step="date")
        elif step == "date" and action == "custom":
            data["step"] = "date_input"
        elif step == "date" and action == "now":
            data.update(occurred_at=now.isoformat(), step="description")
        elif step == "description" and action == "skip":
            data.update(description="", step="confirmation")
        elif step == "confirmation" and action == "confirm":
            await use_case.create_transaction(
                CreateFinanceTransactionParams(
                    owner_username=connection.owner_username,
                    now=now,
                    draft=self.draft(data),
                    actor=self.actor(connection, data["id"], data["month_id"]),
                ),
            )
            await transaction.commit()
            data["step"] = "done"
        else:
            raise ValueError

    async def show(
        self,
        *,
        message: Message,
        data: dict[str, Any],
        month: FinanceMonth,
        language: LanguageEnum,
    ) -> None:
        step = data["step"]
        rows = []
        title, options = self.content(data=data, month=month, language=language)
        for label, action in options:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=label,
                        callback_data=f"fin:{data['id']}:{data['revision']}:{action}",
                    ),
                ],
            )
        controls = []
        if step != "kind":
            controls.append(
                InlineKeyboardButton(
                    text=FinanceConversationText.BACK.get_translation(language),
                    callback_data=f"fin:{data['id']}:{data['revision']}:back",
                ),
            )
        controls.append(
            InlineKeyboardButton(
                text=FinanceConversationText.CANCEL.get_translation(language),
                callback_data=f"fin:{data['id']}:{data['revision']}:cancel",
            ),
        )
        rows.append(controls)
        await message.answer(
            title,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode=None,
        )

    def content(
        self,
        *,
        data: dict[str, Any],
        month: FinanceMonth,
        language: LanguageEnum,
    ) -> tuple[str, list[tuple[str, str]]]:
        step = data["step"]
        prompt_key = {"kind": "start", "confirmation": "confirm"}.get(step, step)
        title = FinanceConversationText.from_value(prompt_key).get_translation(language)
        options = []
        if step == "kind":
            options = [
                (kind.get_translation(language), kind.value)
                for kind in (FinanceKind.EXPENSE, FinanceKind.INCOME)
            ]
        elif step == "category":
            options = self.category_options(data=data, month=month, language=language)
            if not options:
                title = FinanceConversationText.EMPTY.get_translation(language)
        elif step == "currency":
            options = [
                (c.value, c.value)
                for c in (month.currency, *(c for c in FinanceCurrency if c != month.currency))
            ]
        elif step == "date":
            options = [
                (text.get_translation(language), text.value)
                for text in (FinanceConversationText.NOW, FinanceConversationText.CUSTOM)
            ]
        elif step == "date_input":
            title = title.format(zone=month.time_zone.key)
        elif step == "description":
            options = [(FinanceConversationText.SKIP.get_translation(language), "skip")]
        elif step == "confirmation":
            draft = self.draft(data)
            category = month.get_category(draft.category_id)
            title = (
                f"{category.kind.get_translation(language)} · {category.name}\n"
                f"{draft.amount} {draft.currency}\n"
                f"{draft.occurred_at.astimezone(month.time_zone):%d.%m.%Y %H:%M} "
                f"({month.time_zone.key})\n"
                f"{draft.description}\n{FinanceConversationText.CONFIRM.get_translation(language)}"
            )
            options = [(FinanceConversationText.CONFIRM.get_translation(language), "confirm")]
        return title, options

    def category_options(
        self,
        *,
        data: dict[str, Any],
        month: FinanceMonth,
        language: LanguageEnum,
    ) -> list[tuple[str, str]]:
        categories = sorted(
            (
                c
                for c in month.categories
                if c.kind == data["kind"] and not c.archived and c.id in data["category_ids"]
            ),
            key=lambda c: (c.position, c.id),
        )
        start = data["page"] * CATEGORY_PAGE_SIZE
        options: list[tuple[str, str]] = [
            (c.name, f"cat_{data['category_ids'].index(c.id)}")
            for c in categories[start : start + CATEGORY_PAGE_SIZE]
        ]
        if start:
            options.append(
                (
                    FinanceConversationText.PREVIOUS.get_translation(language),
                    f"page_{data['page'] - 1}",
                ),
            )
        if start + CATEGORY_PAGE_SIZE < len(categories):
            options.append(
                (
                    FinanceConversationText.NEXT.get_translation(language),
                    f"page_{data['page'] + 1}",
                ),
            )
        return options


@inject
async def handle_finance(
    event: Message | CallbackQuery,
    use_case: FromDishka[FinanceUseCase],
    transaction: FromDishka[TelegramTransaction],
    current_datetime: FromDishka[datetime],
    conversation: FinanceConversation,
) -> None:
    await conversation.process(
        event=event,
        use_case=use_case,
        transaction=transaction,
        now=current_datetime,
    )


def create_finance_router() -> Router:
    router = Router(name="telegram_finance")
    router.callback_query.register(handle_finance, F.data.startswith("fin:"))
    router.message.register(handle_finance, F.chat.type == ChatType.PRIVATE)
    return router
