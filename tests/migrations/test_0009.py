from collections.abc import Generator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from infra.postgresql.utils import downgrade, migrate


@pytest.fixture
def before_vault_index() -> Generator[None]:
    migrate(revision="0008")
    yield
    downgrade(revision="base")


async def test_vault_index_upgrade_and_downgrade_preserve_entries(
    engine: AsyncEngine,
    before_vault_index: None,
) -> None:
    _ = before_vault_index
    metadata = sa.MetaData()
    async with engine.begin() as connection:
        await connection.run_sync(metadata.reflect)
        table = metadata.tables["knowledge__knowledge_item_model"]
        await connection.execute(
            sa.insert(table).values(
                id="a" * 32,
                kind="PERSON",
                author_username="owner",
                display_name="Person",
                description="Notes",
                created_at=datetime(2026, 9, 1, tzinfo=UTC),
                updated_at=datetime(2026, 9, 2, tzinfo=UTC),
            ),
        )
    migrate(revision="0009")
    async with engine.begin() as connection:
        indexes = await connection.run_sync(lambda conn: sa.inspect(conn).get_indexes(table.name))
        assert any(index["name"] == "knowledge_items_author_updated_id_idx" for index in indexes)
        assert (await connection.execute(sa.select(table.c.display_name))).scalar_one() == "Person"
    downgrade(revision="0008")
    async with engine.begin() as connection:
        indexes = await connection.run_sync(lambda conn: sa.inspect(conn).get_indexes(table.name))
        assert all(index["name"] != "knowledge_items_author_updated_id_idx" for index in indexes)
        assert (await connection.execute(sa.select(table.c.display_name))).scalar_one() == "Person"
