import asyncio
from dataclasses import dataclass

from aiogram import Bot

from core.telegram.enums import TelegramRuntimeStatus
from infra.config.constants import constants
from infra.config.loggers import log_sanitized_exception
from infra.config.settings import settings
from infra.valkey.telegram_runtime import TelegramRuntimeStatusStore


@dataclass(kw_only=True, slots=True)
class TelegramRuntimeState:
    status: TelegramRuntimeStatus


@dataclass(kw_only=True, slots=True)
class TelegramBotRuntime:
    bot: Bot
    state: TelegramRuntimeState
    status_store: TelegramRuntimeStatusStore

    async def register_webhook(self) -> None:
        accepted = await self.bot.set_webhook(
            url=settings.app.get_url("api/personal-workspace/telegram/webhook"),
            secret_token=settings.telegram.webhook_secret.get_secret_value(),
            allowed_updates=["message", "callback_query"],
        )
        if not accepted:
            msg = "Telegram webhook registration was not accepted"
            raise RuntimeError(msg)

    async def run(self) -> None:
        registered = False
        while True:
            try:
                await self.status_store.publish(self.state.status)
                async with asyncio.timeout(constants.telegram.connection_timeout_seconds):
                    if registered:
                        await self.bot.get_me()
                    else:
                        await self.register_webhook()
                        registered = True
                await self.status_store.publish(TelegramRuntimeStatus.READY)
                self.state.status = TelegramRuntimeStatus.READY
            except Exception as exc:  # noqa: BLE001
                registered = False
                self.state.status = TelegramRuntimeStatus.FAILED
                log_sanitized_exception(event="Telegram connection failed", error=exc)
                try:
                    await self.status_store.publish(TelegramRuntimeStatus.FAILED)
                except Exception as store_error:  # noqa: BLE001
                    log_sanitized_exception(
                        event="Telegram runtime status could not be published",
                        error=store_error,
                    )
                await asyncio.sleep(constants.telegram.connection_retry_seconds)
            else:
                await asyncio.sleep(constants.telegram.connection_check_seconds)
