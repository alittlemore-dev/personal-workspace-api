from collections.abc import Awaitable
from dataclasses import dataclass
from typing import cast

from valkey.asyncio import Valkey

from core.telegram.storages import TelegramRedemptionLimiter

_ATTEMPT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


@dataclass(kw_only=True, slots=True)
class ValkeyTelegramRedemptionLimiter(TelegramRedemptionLimiter):
    valkey: Valkey
    limit: int
    window_seconds: int

    async def allow_attempt(self, *, telegram_user_id: int) -> bool:
        count = await cast(
            "Awaitable[int]",
            self.valkey.eval(
                _ATTEMPT_SCRIPT,
                1,
                f"telegram:invitation-attempt:{telegram_user_id}",
                str(self.window_seconds),
            ),
        )
        return count <= self.limit
