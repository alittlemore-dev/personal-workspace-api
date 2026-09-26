from unittest.mock import AsyncMock

import pytest

from infra.valkey.telegram_limiter import ValkeyTelegramRedemptionLimiter


@pytest.mark.asyncio
async def test_redemption_limiter_rejects_attempt_after_limit() -> None:
    valkey = AsyncMock()
    valkey.eval.side_effect = [1, 10, 11]
    limiter = ValkeyTelegramRedemptionLimiter(valkey=valkey, limit=10, window_seconds=900)

    assert await limiter.allow_attempt(telegram_user_id=42)
    assert await limiter.allow_attempt(telegram_user_id=42)
    assert not await limiter.allow_attempt(telegram_user_id=42)
    assert valkey.eval.await_count == 3
    assert valkey.eval.call_args.args[2] == "telegram:invitation-attempt:42"
    assert valkey.eval.call_args.args[3] == "900"
