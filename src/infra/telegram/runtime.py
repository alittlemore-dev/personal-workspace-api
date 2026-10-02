import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import DeleteWebhook, GetMe, SetWebhook

from core.telegram.enums import TelegramRuntimeStatus
from infra.config.constants import constants
from infra.config.loggers import log_sanitized_exception
from infra.config.settings import settings
from infra.telegram.bot import TRANSPORT_ERRORS, TelegramFailoverSession
from infra.telegram.commands import TelegramCommandMenu
from infra.telegram.polling import TelegramPollingReceiver
from infra.valkey.telegram_delivery import TelegramDeliveryLease
from infra.valkey.telegram_runtime import TelegramRuntimeStatusStore


@dataclass(kw_only=True, slots=True)
class TelegramRuntimeState:
    status: TelegramRuntimeStatus


@dataclass(kw_only=True, slots=True)
class TelegramBotRuntime:
    bot: Bot
    state: TelegramRuntimeState
    status_store: TelegramRuntimeStatusStore
    delivery_lease: TelegramDeliveryLease
    handle_update: Callable[[dict[str, object]], Awaitable[None]]

    async def register_webhook(self, index: int) -> None:
        session = self.transport
        accepted = await session.set_webhook(
            self.bot,
            index,
            SetWebhook(
                url=settings.app.get_url("api/personal-workspace/telegram/webhook"),
                secret_token=settings.telegram.webhook_secret.get_secret_value(),
                allowed_updates=list(constants.telegram.allowed_updates),
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
                        if settings.telegram.delivery_mode == "webhook":
                            await self.register_webhook(index)
                        elif not await session.request_candidate(
                            bot=self.bot,
                            method=DeleteWebhook(drop_pending_updates=False),
                            index=index,
                        ):
                            msg = "Telegram webhook removal was not accepted"
                            raise RuntimeError(msg)
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

    async def monitor(self) -> None:
        active: int | None = None
        registered: int | None = None
        backup_cursor = 0
        command_menu = TelegramCommandMenu(
            bot=self.bot,
            transport=self.transport,
            registered=False,
            next_attempt_at=0,
        )
        while True:
            self.transport.wake.clear()
            try:
                await self.delivery_lease.ensure_owned()
                shared = await self.status_store.get_ready_route()
                active = await self.connect(shared if shared is not None else active, registered)
                registered = active
                await self.delivery_lease.ensure_owned()
                await self.status_store.publish_ready(active)
                self.state.status = TelegramRuntimeStatus.READY
                await command_menu.configure(active)
                backup_cursor = await self.check_backup(active, backup_cursor)
            except Exception as exc:  # noqa: BLE001
                await self.delivery_lease.ensure_owned()
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

    async def run(self) -> None:
        while True:
            acquired = False
            try:
                acquired = await self.delivery_lease.acquire()
                if not acquired:
                    self.state.status = (
                        TelegramRuntimeStatus.READY
                        if await self.status_store.is_ready()
                        else TelegramRuntimeStatus.CONNECTING
                    )
                    await self.wait(constants.telegram.delivery_lease_retry_seconds)
                    continue
                self.state.status = TelegramRuntimeStatus.CONNECTING
                async with asyncio.TaskGroup() as tasks:
                    tasks.create_task(
                        self.delivery_lease.keep_alive(),
                        name="telegram-delivery-lease",
                    )
                    if settings.telegram.delivery_mode == "polling":
                        tasks.create_task(
                            TelegramPollingReceiver(runtime=self).run(),
                            name="telegram-polling",
                        )
                    else:
                        tasks.create_task(self.monitor(), name="telegram-webhook-monitor")
            except Exception as exc:  # noqa: BLE001
                self.state.status = TelegramRuntimeStatus.FAILED
                log_sanitized_exception(
                    event="Telegram delivery failed",
                    error=exc,
                    delivery_mode=settings.telegram.delivery_mode,
                    failure_types=(
                        [type(error).__name__ for error in exc.exceptions]
                        if isinstance(exc, ExceptionGroup)
                        else [type(exc).__name__]
                    ),
                )
            finally:
                if acquired:
                    try:
                        await self.delivery_lease.release()
                    except Exception as exc:  # noqa: BLE001
                        log_sanitized_exception(event="Telegram delivery release failed", error=exc)
            await self.wait(constants.telegram.connection_retry_seconds)
