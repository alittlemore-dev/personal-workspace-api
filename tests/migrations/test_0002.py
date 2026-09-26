from collections.abc import Generator
from typing import Protocol, TypedDict, cast

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from infra.postgresql.utils import downgrade, migrate


class ReflectedEnum(TypedDict):
    name: str


class PostgreSQLInspector(Protocol):
    def get_table_names(self) -> list[str]: ...

    def get_enums(self) -> list[ReflectedEnum]: ...

    def get_foreign_keys(self, table_name: str) -> list[object]: ...


@pytest.fixture
def migrated_to_0002() -> Generator[None]:
    migrate(revision="0002")
    yield
    downgrade(revision="base")


def inspect_telegram_schema(connection: Connection) -> tuple[set[str], set[str], int]:
    inspector = cast("PostgreSQLInspector", sa.inspect(connection))
    tables = set(inspector.get_table_names())
    enums = {item["name"] for item in inspector.get_enums()}
    foreign_keys = len(inspector.get_foreign_keys("telegram__telegram_connection_model"))
    return tables, enums, foreign_keys


def inspect_telegram_absence(connection: Connection) -> tuple[set[str], set[str]]:
    inspector = cast("PostgreSQLInspector", sa.inspect(connection))
    return set(inspector.get_table_names()), {item["name"] for item in inspector.get_enums()}


async def test_telegram_migration_owns_tables_without_cross_service_foreign_key(
    engine: AsyncEngine,
    migrated_to_0002: None,
) -> None:
    _ = migrated_to_0002
    async with engine.connect() as connection:
        tables, enums, foreign_keys = await connection.run_sync(inspect_telegram_schema)
    assert "telegram__telegram_invitation_model" in tables
    assert "telegram__telegram_connection_model" in tables
    assert "telegram_connection_state_enum" in enums
    assert foreign_keys == 0

    downgrade(revision="0001")
    async with engine.connect() as connection:
        remaining = await connection.run_sync(inspect_telegram_absence)
    assert "telegram__telegram_connection_model" not in remaining[0]
    assert "telegram__telegram_invitation_model" not in remaining[0]
    assert "telegram_connection_state_enum" not in remaining[1]
