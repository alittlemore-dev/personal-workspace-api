import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.test_cases import StorageTestCase


class TestQueryPlanReadOnlyTransaction(StorageTestCase):
    async def test_read_only_transaction_rejects_mutation_before_execution(self) -> None:
        await self.db_session.execute(text("SET TRANSACTION READ ONLY"))

        with pytest.raises(DBAPIError, match="read-only transaction"):
            await self.db_session.execute(
                text("DELETE FROM knowledge__knowledge_item_model"),
            )
