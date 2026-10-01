import hashlib
from dataclasses import dataclass
from typing import Self

from valkey.asyncio import Valkey
from valkey.exceptions import ValkeyError

from core.telegram.enums import TelegramRuntimeStatus
from infra.config.constants import constants
from infra.config.settings import settings


@dataclass(kw_only=True, slots=True)
class TelegramRuntimeStatusStore:
    valkey: Valkey
    key: str
    ttl_seconds: int

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
        )

    async def publish(self, status: TelegramRuntimeStatus) -> None:
        await self.valkey.set(self.key, status.value, ex=self.ttl_seconds)

    async def is_ready(self) -> bool:
        try:
            value = await self.valkey.get(self.key)
            return isinstance(value, bytes) and value == TelegramRuntimeStatus.READY.value.encode()
        except ValkeyError, OSError:
            return False

    async def close(self) -> None:
        await self.valkey.aclose(close_connection_pool=True)
