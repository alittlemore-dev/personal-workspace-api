import asyncio
from contextlib import suppress
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import GetMe, SetWebhook

from core.telegram.enums import TelegramRuntimeStatus
from infra.config.constants import constants
from infra.config.loggers import log_sanitized_exception
from infra.config.settings import settings
from infra.telegram.bot import TRANSPORT_ERRORS, TelegramFailoverSession
from infra.valkey.telegram_runtime import TelegramRuntimeStatusStore


@dataclass(kw_only=True, slots=True)
class TelegramRuntimeState:
    status: TelegramRuntimeStatus


@dataclass(kw_only=True, slots=True)
class TelegramBotRuntime:
    bot: Bot
    state: TelegramRuntimeState
    status_store: TelegramRuntimeStatusStore

    async def register_webhook(self, index: int) -> None:
        session = self.transport
        accepted = await session.set_webhook(
            self.bot,
            index,
            SetWebhook(
                url=settings.app.get_url("api/personal-workspace/telegram/webhook"),
                secret_token=settings.telegram.webhook_secret.get_secret_value(),
                allowed_updates=["message", "callback_query"],
            ),
        )
        if not accepted:
            msg = "Telegram webhook registration was not accepted"
            raise RuntimeError(msg)

    @property
    def transport(self) -> TelegramFailoverSession:
        if not isinstance(self.bot.session, TelegramFailoverSession):
            msg = "Telegram runtime requires a failover transport"
            raise TypeError(msg)
        return self.bot.session

    async def connect(self, preferred: int | None, registered: int | None) -> int:
        session = self.transport
        candidates = list(range(len(session.routes)))
        if preferred is not None:
            candidates.remove(preferred)
            candidates.insert(0, preferred)
        for index in candidates:
            if not session.candidate_available(index):
                continue
            try:
                async with asyncio.timeout(constants.telegram.connection_timeout_seconds):
                    await session.probe(self.bot, index)
                    if registered != index:
                        await self.register_webhook(index)
            except TRANSPORT_ERRORS:
                await session.mark_failed(index, notify_monitor=False)
            else:
                return index
        raise TelegramNetworkError(method=GetMe(), message="No healthy Telegram route is available")

    async def check_backup(self, active: int, cursor: int) -> int:
        session = self.transport
        for offset in range(len(session.routes)):
            index = (cursor + offset) % len(session.routes)
            if index == active or not session.candidate_available(index):
                continue
            try:
                async with asyncio.timeout(constants.telegram.connection_timeout_seconds):
                    await session.probe(self.bot, index)
            except TRANSPORT_ERRORS as exc:
                await session.mark_failed(index, notify_monitor=False)
                log_sanitized_exception(event="Telegram backup check failed", error=exc)
            except Exception as exc:  # noqa: BLE001
                log_sanitized_exception(event="Telegram backup check failed", error=exc)
            return (index + 1) % len(session.routes)
        return cursor

    async def wait(self, delay: int) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(self.transport.wake.wait(), timeout=delay)

    async def run(self) -> None:
        active: int | None = None
        registered: int | None = None
        backup_cursor = 0
        while True:
            self.transport.wake.clear()
            try:
                shared = await self.status_store.get_ready_route()
                active = await self.connect(shared if shared is not None else active, registered)
                registered = active
                await self.status_store.publish_ready(active)
                self.state.status = TelegramRuntimeStatus.READY
                backup_cursor = await self.check_backup(active, backup_cursor)
            except Exception as exc:  # noqa: BLE001
                registered = None
                self.state.status = TelegramRuntimeStatus.FAILED
                log_sanitized_exception(event="Telegram connection failed", error=exc)
                try:
                    await self.status_store.publish(TelegramRuntimeStatus.FAILED)
                except Exception as store_error:  # noqa: BLE001
                    log_sanitized_exception(
                        event="Telegram runtime status could not be published",
                        error=store_error,
                    )
                await self.wait(constants.telegram.connection_retry_seconds)
            else:
                await self.wait(constants.telegram.connection_check_seconds)
