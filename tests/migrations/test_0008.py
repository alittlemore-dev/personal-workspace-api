from collections.abc import Generator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from infra.postgresql.utils import downgrade, migrate
from tests.helpers.factories.migrations import MigrationFactoryHelper


@pytest.fixture
def finance_before_telegram() -> Generator[None]:
    migrate(revision="0006")
    yield
    downgrade(revision="base")


async def test_finance_telegram_upgrade_preserves_existing_transactions(
    engine: AsyncEngine,
    finance_before_telegram: None,
) -> None:
    _ = finance_before_telegram
    factory = MigrationFactoryHelper()
    async with engine.begin() as connection:
        rows = await factory.finance_rows(connection, False)
        old_metadata = sa.MetaData()
        await connection.run_sync(old_metadata.reflect)
        telegram = old_metadata.tables["telegram__telegram_connection_model"]
        instant = datetime(2026, 9, 15, tzinfo=UTC)
        await connection.execute(
            sa.insert(telegram).values(
                id="c" * 32,
                owner_username="owner",
                telegram_user_id=42,
                private_chat_id=42,
                label="Family",
                first_name="Boris",
                username="boris",
                state="ACTIVE",
                requested_at=instant,
                connected_at=instant,
                state_changed_at=instant,
                last_contact_at=instant,
                notify_birthday=True,
                notify_memorable_date=True,
                language="RU",
            ),
        )
    migrate(revision="0007")
    migrate(revision="0008")
    metadata = sa.MetaData()
    async with engine.begin() as connection:
        await connection.run_sync(metadata.reflect)
        table = metadata.tables["finance__finance_transaction_model"]
        row = (await connection.execute(sa.select(table))).mappings().one()
        assert row["source"] == "WEB"
        assert row["author_id"] == row["author_label"] == row["author_username"]
        assert row["operation_id"] == ""
        telegram = metadata.tables["telegram__telegram_connection_model"]
        settings = (await connection.execute(sa.select(telegram))).mappings().one()
        assert settings["notify_finance_transaction"] is False
        assert settings["notify_finance_limit"] is False
        assert settings["notify_birthday"] is True
        assert settings["notify_memorable_date"] is True
        assert settings["language"] == "RU"
        for name, value in rows.expected_rows["finance_transaction"].items():
            assert row[name] == value
    downgrade(revision="0007")
    downgraded = sa.MetaData()
    async with engine.connect() as connection:
        await connection.run_sync(downgraded.reflect)
        table = downgraded.tables["finance__finance_transaction_model"]
        assert (
            dict((await connection.execute(sa.select(table))).mappings().one())
            == rows.expected_rows["finance_transaction"]
        )
    migrate(revision="0008")
