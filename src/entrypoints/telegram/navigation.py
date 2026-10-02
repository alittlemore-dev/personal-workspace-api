from dataclasses import dataclass

from aiogram import Bot, F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import BaseEventIsolation, BaseStorage
from aiogram.types import Message, ReplyKeyboardRemove
from dishka.integrations.aiogram import FromDishka, inject

from core.i18n.enums import LanguageEnum
from core.telegram.exceptions import TelegramAccessError, TelegramServiceError
from core.telegram.schemas import ResolveTelegramConnectionParams
from core.telegram.storages import TelegramTransaction
from core.telegram.use_cases import TelegramUseCase
from entrypoints.telegram.enums import (
    FinanceConversationText,
    TelegramNavigationAction,
    TelegramNavigationText,
)
from entrypoints.telegram.keyboards import conversation_key, main_keyboard, navigation_action


@dataclass(kw_only=True, slots=True)
class TelegramNavigation:
    bot: Bot
    storage: BaseStorage
    isolation: BaseEventIsolation

    async def process(
        self,
        *,
        message: Message,
        use_case: TelegramUseCase,
        transaction: TelegramTransaction,
    ) -> bool:
        if message.from_user is None:
            return False
        try:
            connection = await use_case.resolve_active_connection(
                params=ResolveTelegramConnectionParams(
                    telegram_user_id=message.from_user.id,
                    private_chat_id=message.chat.id,
                ),
            )
            await transaction.commit()
        except TelegramAccessError:
            await transaction.rollback()
            await message.answer(
                TelegramNavigationText.ACCESS.get_translation(LanguageEnum.EN),
                reply_markup=ReplyKeyboardRemove(),
                parse_mode=None,
            )
            return False
        except TelegramServiceError:
            await transaction.rollback()
            await message.answer(
                TelegramNavigationText.RETRY.get_translation(LanguageEnum.EN),
                parse_mode=None,
            )
            return False
        action = navigation_action(message.text or "")
        key = conversation_key(self.bot.id, connection)
        async with self.isolation.lock(key=key):
            state = FSMContext(storage=self.storage, key=key)
            data = await state.get_data()
            if action == TelegramNavigationAction.CANCEL:
                await state.clear()
                prompt = (
                    FinanceConversationText.CANCELED
                    if data
                    else TelegramNavigationText.NOTHING_TO_CANCEL
                )
            elif action == TelegramNavigationAction.FINANCE:
                prompt = TelegramNavigationText.FINANCE_ENTRY
            elif action == TelegramNavigationAction.MENU:
                prompt = TelegramNavigationText.MENU
            elif action == TelegramNavigationAction.HELP:
                prompt = TelegramNavigationText.HELP_MESSAGE
            elif data and not (message.text or "").startswith("/"):
                return True
            else:
                prompt = TelegramNavigationText.UNKNOWN
            await message.answer(
                prompt.get_translation(connection.language),
                reply_markup=main_keyboard(connection.language),
                parse_mode=None,
            )
        return action == TelegramNavigationAction.FINANCE


@inject
async def handle_navigation(
    message: Message,
    use_case: FromDishka[TelegramUseCase],
    transaction: FromDishka[TelegramTransaction],
    navigation: TelegramNavigation,
) -> None:
    if await navigation.process(message=message, use_case=use_case, transaction=transaction):
        raise SkipHandler


def create_navigation_router() -> Router:
    router = Router(name="telegram_navigation")
    router.message.register(handle_navigation, F.chat.type == ChatType.PRIVATE)
    return router
