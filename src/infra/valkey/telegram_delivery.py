import asyncio
import hashlib
import json
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Self, cast
from uuid import uuid4

from core.telegram.enums import TelegramRuntimeStatus
from infra.config.constants import constants
from infra.config.settings import settings
from infra.valkey.telegram_runtime import TelegramRuntimeStatusStore

RENEW_DELIVERY_SCRIPT = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 1
"""

RELEASE_DELIVERY_SCRIPT = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[3])
redis.call('DEL', KEYS[1])
return 1
"""


class TelegramDeliveryLeaseLostError(RuntimeError):
    pass


@dataclass(kw_only=True, slots=True)
class TelegramDeliveryLease:
    store: TelegramRuntimeStatusStore
    key: str
    token: str
    ttl_seconds: int

    @classmethod
    def create(cls, store: TelegramRuntimeStatusStore) -> Self:
        # Delivery ownership spans slots, proxy pools, and transport modes for one bot.
        identity = hashlib.sha256(
            settings.telegram.bot_token.get_secret_value().encode(),
        ).hexdigest()
        return cls(
            store=store,
            key=f"{constants.telegram.delivery_lease_key_prefix}{identity}",
            token=uuid4().hex,
            ttl_seconds=constants.telegram.delivery_lease_ttl_seconds,
        )

    async def acquire(self) -> bool:
        return bool(
            await self.store.valkey.set(self.key, self.token, nx=True, ex=self.ttl_seconds),
        )

    async def ensure_owned(self) -> None:
        if await self.store.valkey.get(self.key) != self.token.encode():
            msg = "Telegram delivery ownership was lost"
            raise TelegramDeliveryLeaseLostError(msg)

    async def keep_alive(self) -> None:
        while True:
            await asyncio.sleep(constants.telegram.delivery_lease_refresh_seconds)
            renewed = await cast(
                "Awaitable[int]",
                self.store.valkey.eval(
                    RENEW_DELIVERY_SCRIPT,
                    1,
                    self.key,
                    self.token,
                    str(self.ttl_seconds),
                ),
            )
            if renewed != 1:
                msg = "Telegram delivery ownership could not be renewed"
                raise TelegramDeliveryLeaseLostError(msg)

    async def release(self) -> None:
        await cast(
            "Awaitable[int]",
            self.store.valkey.eval(
                RELEASE_DELIVERY_SCRIPT,
                2,
                self.key,
                self.store.key,
                self.token,
                json.dumps({"status": TelegramRuntimeStatus.FAILED.value}),
                str(self.store.ttl_seconds),
            ),
        )
