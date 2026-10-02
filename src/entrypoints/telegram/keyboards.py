from aiogram.fsm.storage.base import StorageKey
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from core.i18n.enums import LanguageEnum
from core.telegram.schemas import TelegramConnection
from entrypoints.telegram.enums import TelegramNavigationAction, TelegramNavigationText


def main_keyboard(language: LanguageEnum) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=TelegramNavigationText.FINANCE.get_translation(language))],
            [
                KeyboardButton(text=TelegramNavigationText.HELP.get_translation(language)),
                KeyboardButton(text=TelegramNavigationText.CANCEL.get_translation(language)),
            ],
        ],
        is_persistent=True,
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def conversation_key(bot_id: int, connection: TelegramConnection) -> StorageKey:
    return StorageKey(
        bot_id=bot_id,
        chat_id=connection.private_chat_id,
        user_id=connection.telegram_user_id,
        destiny=f"{connection.owner_username}:{connection.id}",
    )


def navigation_action(text: str) -> TelegramNavigationAction:
    commands = {
        "/start": TelegramNavigationAction.MENU,
        "/menu": TelegramNavigationAction.MENU,
        "/finance": TelegramNavigationAction.FINANCE,
        "/help": TelegramNavigationAction.HELP,
        "/cancel": TelegramNavigationAction.CANCEL,
    }
    command = text.split(" ", 1)[0].split("@", 1)[0]
    if command in commands:
        return commands[command]
    for label in (
        TelegramNavigationText.FINANCE,
        TelegramNavigationText.HELP,
        TelegramNavigationText.CANCEL,
    ):
        if text in (label.value_ru, label.value_en):
            return TelegramNavigationAction(label.value)
    return TelegramNavigationAction.UNKNOWN
