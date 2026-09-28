from collections.abc import Generator
from datetime import date
from typing import Protocol, TypedDict, cast

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from infra.postgresql.utils import downgrade, migrate


class ReflectedEnum(TypedDict):
    name: str


class PostgreSQLInspector(Protocol):
    def get_table_names(self) -> list[str]: ...

    def get_enums(self) -> list[ReflectedEnum]: ...


@pytest.fixture
def migrated_to_0003() -> Generator[None]:
    migrate(revision="0003")
    yield
    downgrade(revision="base")


def inspect_calendar_tables(connection: Connection) -> tuple[set[str], set[str]]:
    inspector = cast("PostgreSQLInspector", sa.inspect(connection))
    return set(inspector.get_table_names()), {value["name"] for value in inspector.get_enums()}


async def test_calendar_workspace_migration_upgrades_and_downgrades(
    engine: AsyncEngine,
    migrated_to_0003: None,
) -> None:
    _ = migrated_to_0003
    migrate(revision="0004")
    async with engine.begin() as connection:
        tables, enums = await connection.run_sync(inspect_calendar_tables)
        assert {"event_model", "important_info_model"} <= tables
        assert "event_frequency_enum" in enums
        important_info = sa.table(
            "important_info_model",
            sa.column("id", sa.String()),
            sa.column("author_username", sa.String()),
            sa.column("text", sa.String()),
            sa.column("position", sa.Integer()),
        )
        event = sa.table(
            "event_model",
            sa.column("id", sa.String()),
            sa.column("author_username", sa.String()),
            sa.column("title", sa.String()),
            sa.column("description", sa.String()),
            sa.column("anchor_time_zone", sa.String()),
            sa.column("all_day", sa.Boolean()),
            sa.column("start_date", sa.Date()),
            sa.column("end_date", sa.Date()),
            sa.column(
                "frequency",
                postgresql.ENUM(
                    "none",
                    "daily",
                    "weekly",
                    "monthly",
                    "yearly",
                    name="event_frequency_enum",
                    create_type=False,
                ),
            ),
        )
        await connection.execute(
            sa.insert(important_info).values(
                id="a" * 32,
                author_username="owner",
                text="Remember",
                position=0,
            ),
        )
        await connection.execute(
            sa.insert(event).values(
                id="b" * 32,
                author_username="owner",
                title="Holiday",
                description="",
                anchor_time_zone="UTC",
                all_day=True,
                start_date=date(2026, 12, 25),
                end_date=date(2026, 12, 26),
                frequency="none",
            ),
        )
        assert (await connection.scalar(sa.select(important_info.c.text))) == "Remember"
        assert (await connection.scalar(sa.select(event.c.title))) == "Holiday"

    downgrade(revision="0003")
    async with engine.connect() as connection:
        tables, enums = await connection.run_sync(inspect_calendar_tables)
    assert "event_model" not in tables
    assert "important_info_model" not in tables
    assert "event_frequency_enum" not in enums
