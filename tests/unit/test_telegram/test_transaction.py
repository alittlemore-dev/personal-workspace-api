from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from core.telegram.exceptions import TelegramServiceError
from infra.postgresql.telegram_transaction import TelegramDatabaseTransaction


@pytest.mark.asyncio
async def test_failed_connection_commit_rolls_back_before_bot_acknowledges() -> None:
    session = AsyncMock()
    session.commit.side_effect = SQLAlchemyError("commit failed")
    transaction = TelegramDatabaseTransaction(session=session)

    with pytest.raises(TelegramServiceError):
        await transaction.commit()

    session.rollback.assert_awaited_once_with()
