import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import GetUpdates
from aiogram.types import Update

from core.telegram.enums import TelegramRuntimeStatus
from infra.config.constants import constants
from infra.config.loggers import log_sanitized_exception, logger
from infra.telegram.bot import TRANSPORT_ERRORS

if TYPE_CHECKING:
    from infra.telegram.runtime import TelegramBotRuntime


@dataclass(kw_only=True, slots=True)
class TelegramPollingReceiver:
    runtime: TelegramBotRuntime

    async def dispatch(self, update: Update) -> Exception | None:
        try:
            await self.runtime.handle_update(update.model_dump(mode="json", exclude_none=True))
        except Exception as exc:  # noqa: BLE001
            log_sanitized_exception(
                event="Telegram update handling failed",
                error=exc,
                update_id=update.update_id,
            )
            return exc
        return None

    async def run(self) -> None:
        runtime = self.runtime
        active: int | None = None
        registered: int | None = None
        offset: int | None = None
        backup_cursor = 0
        while True:
            runtime.transport.wake.clear()
            try:
                await runtime.delivery_lease.ensure_owned()
                if active is not None and not runtime.transport.candidate_available(active):
                    active = None
                if active is None:
                    shared = await runtime.status_store.get_ready_route()
                    active = await runtime.connect(shared, registered)
                    registered = active
                updates = await runtime.transport.request_route(
                    bot=runtime.bot,
                    method=GetUpdates(
                        offset=offset,
                        timeout=(
                            constants.telegram.polling_timeout_seconds
                            if runtime.state.status == TelegramRuntimeStatus.READY
                            else 0
                        ),
                        allowed_updates=list(constants.telegram.allowed_updates),
                    ),
                    index=active,
                    request_timeout=(
                        constants.telegram.polling_timeout_seconds
                        + constants.telegram.connection_timeout_seconds
                    ),
                )
                await runtime.delivery_lease.ensure_owned()
                await runtime.status_store.publish_ready(active)
                if runtime.state.status != TelegramRuntimeStatus.READY:
                    logger.info("Telegram polling connected", route_index=active)
                runtime.state.status = TelegramRuntimeStatus.READY
                for update in updates:
                    await runtime.delivery_lease.ensure_owned()
                    error = await self.dispatch(update)
                    # A handler may have committed or sent a reply before failing.
                    offset = update.update_id + 1
                    if isinstance(error, (*TRANSPORT_ERRORS, TelegramRetryAfter)):
                        raise error
                backup_cursor = await runtime.check_backup(active, backup_cursor)
            except (*TRANSPORT_ERRORS, TelegramRetryAfter) as exc:
                await runtime.delivery_lease.ensure_owned()
                if active is not None and not isinstance(exc, TelegramRetryAfter):
                    await runtime.transport.mark_failed(active, notify_monitor=False)
                active = None
                registered = None
                runtime.state.status = TelegramRuntimeStatus.FAILED
                await runtime.status_store.publish(TelegramRuntimeStatus.FAILED)
                log_sanitized_exception(event="Telegram polling connection failed", error=exc)
                if isinstance(exc, TelegramRetryAfter):
                    await asyncio.sleep(exc.retry_after)
                else:
                    await runtime.wait(constants.telegram.connection_retry_seconds)
