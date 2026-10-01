from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNotFound,
    TelegramRetryAfter,
    TelegramUnauthorizedError,
)

from core.notifications.clients import (
    PermanentReminderSendError,
    ReminderSender,
    RetryableReminderSendError,
)
from infra.config.constants import constants


@dataclass(kw_only=True, slots=True)
class AiogramReminderSender(ReminderSender):
    bot: Bot

    async def send(self, *, private_chat_id: int, text: str) -> None:
        try:
            await self.bot.send_message(
                chat_id=private_chat_id,
                text=text,
                parse_mode=None,
                request_timeout=constants.telegram.connection_timeout_seconds,
            )
        except TelegramRetryAfter as exc:
            raise RetryableReminderSendError(retry_after_seconds=exc.retry_after) from exc
        except (
            TelegramForbiddenError,
            TelegramBadRequest,
            TelegramUnauthorizedError,
            TelegramNotFound,
        ) as exc:
            raise PermanentReminderSendError from exc
        except TelegramAPIError as exc:
            raise RetryableReminderSendError(retry_after_seconds=0) from exc


class UnavailableReminderSender(ReminderSender):
    async def send(self, *, private_chat_id: int, text: str) -> None:  # noqa: ARG002
        raise RetryableReminderSendError(retry_after_seconds=0)
