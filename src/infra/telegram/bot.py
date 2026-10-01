import asyncio
from collections.abc import AsyncGenerator
from time import monotonic
from typing import Any

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramNetworkError, TelegramServerError
from aiogram.methods import GetMe, SetWebhook, TelegramMethod
from aiogram.methods.base import TelegramType
from aiogram.types import User
from aiohttp_socks import ProxyConnectionError, ProxyError, ProxyTimeoutError
from valkey.exceptions import ValkeyError

from infra.config.constants import constants
from infra.config.loggers import log_sanitized_exception
from infra.config.settings import TelegramSettings
from infra.valkey.telegram_runtime import TelegramRuntimeStatusStore

TRANSPORT_ERRORS = (TelegramNetworkError, TelegramServerError, TimeoutError)
PROXY_ERRORS = (ProxyConnectionError, ProxyTimeoutError, ProxyError)


class TelegramFailoverSession(BaseSession):
    def __init__(
        self,
        *,
        telegram_settings: TelegramSettings,
        runtime_status: TelegramRuntimeStatusStore,
    ) -> None:
        super().__init__(timeout=constants.telegram.connection_timeout_seconds)
        self.pool_id = telegram_settings.proxy_pool_id
        self.routes = tuple(
            AiohttpSession(proxy=proxy.get_secret_value(), timeout=self.timeout)
            for proxy in telegram_settings.proxy_urls
        ) or (AiohttpSession(timeout=self.timeout),)
        self.runtime_status = runtime_status
        self.wake = asyncio.Event()
        self.cooldowns: dict[int, float] = {}

    def candidate_available(self, index: int) -> bool:
        return monotonic() >= self.cooldowns.get(index, 0)

    async def probe(self, bot: Bot, index: int) -> User:
        return await self.request_candidate(bot=bot, method=GetMe(), index=index)

    async def set_webhook(self, bot: Bot, index: int, method: SetWebhook) -> bool:
        return await self.request_candidate(bot=bot, method=method, index=index)

    async def request_route(
        self,
        *,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        index: int,
        request_timeout: int | None,
    ) -> TelegramType:
        route = self.routes[index]
        route.api = self.api
        try:
            return await route.make_request(bot, method, timeout=request_timeout)
        except PROXY_ERRORS:
            raise TelegramNetworkError(
                method=method,
                message="Telegram proxy transport failed",
            ) from None

    async def request_candidate(
        self,
        *,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        index: int,
    ) -> TelegramType:
        try:
            return await self.request_route(
                bot=bot,
                method=method,
                index=index,
                request_timeout=None,
            )
        except TRANSPORT_ERRORS:
            self.cooldowns[index] = monotonic() + constants.telegram.proxy_cooldown_seconds
            raise

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,  # noqa: ASYNC109 - aiogram session contract
    ) -> TelegramType:
        index = await self.runtime_status.get_ready_route()
        if index is None or not self.candidate_available(index):
            raise TelegramNetworkError(method=method, message="Telegram transport is unavailable")
        try:
            return await self.request_route(
                bot=bot,
                method=method,
                index=index,
                request_timeout=timeout,
            )
        except TRANSPORT_ERRORS:
            await self.mark_failed(index, notify_monitor=True)
            raise

    async def mark_failed(self, index: int, *, notify_monitor: bool) -> None:
        self.cooldowns[index] = monotonic() + constants.telegram.proxy_cooldown_seconds
        if notify_monitor:
            self.wake.set()
        try:
            await self.runtime_status.mark_failed(index)
        except (ValkeyError, OSError) as exc:
            log_sanitized_exception(
                event="Telegram route failure could not be published",
                error=exc,
            )

    async def close(self) -> None:
        for route in self.routes:
            await route.close()

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,  # noqa: ASYNC109 - aiogram session contract
        chunk_size: int = 65536,
        raise_for_status: bool = True,  # noqa: FBT001, FBT002
    ) -> AsyncGenerator[bytes]:
        index = await self.runtime_status.get_ready_route()
        if index is None or not self.candidate_available(index):
            msg = "Telegram transport is unavailable"
            raise OSError(msg)
        try:
            async for chunk in self.routes[index].stream_content(
                url,
                headers=headers,
                timeout=timeout,
                chunk_size=chunk_size,
                raise_for_status=raise_for_status,
            ):
                yield chunk
        except PROXY_ERRORS:
            await self.mark_failed(index, notify_monitor=True)
            msg = "Telegram proxy transport failed"
            raise OSError(msg) from None
        except OSError, TimeoutError:
            await self.mark_failed(index, notify_monitor=True)
            raise


def create_telegram_bot(
    *,
    telegram_settings: TelegramSettings,
    runtime_status: TelegramRuntimeStatusStore,
) -> Bot:
    return Bot(
        token=telegram_settings.bot_token.get_secret_value(),
        session=TelegramFailoverSession(
            telegram_settings=telegram_settings,
            runtime_status=runtime_status,
        ),
    )
