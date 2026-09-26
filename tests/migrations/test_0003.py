from collections.abc import Generator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from infra.postgresql.utils import downgrade, migrate

connection_state = postgresql.ENUM(
    "PENDING",
    "ACTIVE",
    "REVOKED",
    "BLOCKED",
    name="telegram_connection_state_enum",
    create_type=False,
)
notification_language = postgresql.ENUM(
    "RU",
    "EN",
    name="telegram_notification_language_enum",
    create_type=False,
)
connections = sa.table(
    "telegram__telegram_connection_model",
    sa.column("id", sa.String()),
    sa.column("owner_username", sa.String()),
    sa.column("telegram_user_id", sa.BigInteger()),
    sa.column("private_chat_id", sa.BigInteger()),
    sa.column("label", sa.String()),
    sa.column("first_name", sa.String()),
    sa.column("username", sa.String()),
    sa.column("state", connection_state),
    sa.column("requested_at", sa.DateTime(timezone=True)),
    sa.column("state_changed_at", sa.DateTime(timezone=True)),
    sa.column("last_contact_at", sa.DateTime(timezone=True)),
    sa.column("notify_birthday", sa.Boolean()),
    sa.column("notify_memorable_date", sa.Boolean()),
    sa.column("language", notification_language),
    sa.column("time_zone", sa.String()),
)


@pytest.fixture
def migrated_to_0002() -> Generator[None]:
    migrate(revision="0002")
    yield
    downgrade(revision="base")


async def test_notification_migration_preserves_existing_connection_with_safe_defaults(
    engine: AsyncEngine,
    migrated_to_0002: None,
) -> None:
    _ = migrated_to_0002
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(connections).values(
                id="c" * 32,
                owner_username="owner",
                telegram_user_id=42,
                private_chat_id=42,
                label="Family",
                first_name="Anne",
                username="anne",
                state="ACTIVE",
                requested_at=datetime(2026, 9, 26, tzinfo=UTC),
                state_changed_at=datetime(2026, 9, 26, tzinfo=UTC),
                last_contact_at=datetime(2026, 9, 26, tzinfo=UTC),
            ),
        )

    migrate(revision="0003")
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                sa.select(
                    connections.c.notify_birthday,
                    connections.c.notify_memorable_date,
                    connections.c.language,
                    connections.c.time_zone,
                ).where(connections.c.id == "c" * 32),
            )
        ).one()
        assert row == (False, False, "EN", "UTC")
        assert await connection.run_sync(has_enabled_defaults)

    downgrade(revision="0002")
    async with engine.connect() as connection:
        still_present = (
            await connection.execute(
                sa.select(connections.c.id).where(connections.c.id == "c" * 32),
            )
        ).scalar_one()
        assert still_present == "c" * 32


def has_enabled_defaults(connection: Connection) -> bool:
    inspector = sa.inspect(connection)
    for table_name in ("knowledge__person_details_model", "knowledge__date_details_model"):
        column = next(
            column
            for column in inspector.get_columns(table_name)
            if column["name"] == "notifications_enabled"
        )
        if "true" not in str(column["default"]).lower():
            return False
    return True
