import hashlib
import json
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Self, cast

from valkey.asyncio import Valkey
from valkey.exceptions import ValkeyError

from core.telegram.enums import TelegramRuntimeStatus
from infra.config.constants import constants
from infra.config.settings import settings

MARK_FAILED_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local ok, route = pcall(cjson.decode, raw)
if not ok or type(route) ~= 'table' or route.status ~= 'ready' or route.pool_id ~= ARGV[1]
    or route.route_count ~= tonumber(ARGV[2]) or route.index ~= tonumber(ARGV[3]) then
    return 0
end
redis.call('SET', KEYS[1], ARGV[4], 'EX', ARGV[5])
return 1
"""


@dataclass(kw_only=True, slots=True)
class TelegramRuntimeStatusStore:
    valkey: Valkey
    key: str
    ttl_seconds: int
    pool_id: str
    route_count: int

    @classmethod
    def create(cls) -> Self:
        # The matching auth origin isolates readiness leases between deployment slots.
        scope = hashlib.sha256(settings.auth.verify_url.encode()).hexdigest()
        return cls(
            valkey=Valkey.from_url(
                settings.valkey.get_url(
                    constants.valkey.databases.response_cache,
                ).get_secret_value(),
                socket_timeout=constants.telegram.runtime_store_timeout_seconds,
                socket_connect_timeout=constants.telegram.runtime_store_timeout_seconds,
            ),
            key=f"{constants.telegram.runtime_status_key_prefix}{scope}",
            ttl_seconds=constants.telegram.runtime_status_ttl_seconds,
            pool_id=settings.telegram.proxy_pool_id,
            route_count=max(1, len(settings.telegram.proxy_urls)),
        )

    async def publish(self, status: TelegramRuntimeStatus) -> None:
        if status == TelegramRuntimeStatus.READY:
            msg = "A ready Telegram lease requires an explicit route"
            raise ValueError(msg)
        await self.valkey.set(
            self.key,
            json.dumps({"status": status.value}),
            ex=self.ttl_seconds,
        )

    async def publish_ready(self, index: int) -> None:
        if type(index) is not int or not 0 <= index < self.route_count:
            msg = "Telegram route index is outside the configured pool"
            raise ValueError(msg)
        await self.valkey.set(
            self.key,
            json.dumps(
                {
                    "status": TelegramRuntimeStatus.READY.value,
                    "pool_id": self.pool_id,
                    "route_count": self.route_count,
                    "index": index,
                },
            ),
            ex=self.ttl_seconds,
        )

    async def get_ready_route(self) -> int | None:
        try:
            value = await self.valkey.get(self.key)
            if not isinstance(value, bytes):
                return None
            route = json.loads(value)
            if not isinstance(route, dict):
                return None
            index = route.get("index")
            if (
                route.get("status") == TelegramRuntimeStatus.READY.value
                and route.get("pool_id") == self.pool_id
                and type(route.get("route_count")) is int
                and route["route_count"] == self.route_count
                and type(index) is int
                and 0 <= index < self.route_count
            ):
                return index
        except ValkeyError, OSError, ValueError, TypeError:
            return None
        return None

    async def is_ready(self) -> bool:
        return await self.get_ready_route() is not None

    async def mark_failed(self, index: int) -> bool:
        result = await cast(
            "Awaitable[int]",
            self.valkey.eval(
                MARK_FAILED_SCRIPT,
                1,
                self.key,
                self.pool_id,
                str(self.route_count),
                str(index),
                json.dumps({"status": TelegramRuntimeStatus.FAILED.value}),
                str(self.ttl_seconds),
            ),
        )
        return result == 1

    async def close(self) -> None:
        await self.valkey.aclose(close_connection_pool=True)
