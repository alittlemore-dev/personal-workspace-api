from collections.abc import Generator

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Connection
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.ext.asyncio import AsyncEngine

from infra.postgresql.utils import downgrade, migrate


@pytest.fixture
def migrated_to_0004() -> Generator[None]:
    migrate(revision="0004")
    yield
    downgrade(revision="base")


def time_zone_columns(connection: Connection) -> tuple[set[str], set[str]]:
    inspector: Inspector = sa.inspect(connection)
    connections = {
        column["name"] for column in inspector.get_columns("telegram__telegram_connection_model")
    }
    deliveries = {
        column["name"] for column in inspector.get_columns("notifications__reminder_delivery_model")
    }
    return connections, deliveries


async def test_account_time_zone_migration_replaces_connection_zone_and_adds_schedule(
    engine: AsyncEngine,
    migrated_to_0004: None,
) -> None:
    _ = migrated_to_0004
    migrate(revision="0005")
    async with engine.connect() as connection:
        connections, deliveries = await connection.run_sync(time_zone_columns)
    assert "time_zone" not in connections
    assert "scheduled_at" in deliveries

    downgrade(revision="0004")
    async with engine.connect() as connection:
        connections, deliveries = await connection.run_sync(time_zone_columns)
    assert "time_zone" in connections
    assert "scheduled_at" not in deliveries
