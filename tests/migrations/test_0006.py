from collections.abc import Generator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from infra.postgresql.utils import downgrade, migrate


@pytest.fixture
def migrated_to_0005() -> Generator[None]:
    migrate(revision="0005")
    yield
    downgrade(revision="base")


async def test_finance_migration_seeds_only_category_names(
    engine: AsyncEngine,
    migrated_to_0005: None,
) -> None:
    _ = migrated_to_0005
    migrate(revision="0006")
    template = sa.table(
        "finance_template_category",
        sa.column("kind", sa.String()),
        sa.column("name_ru", sa.String()),
        sa.column("name_en", sa.String()),
    )
    async with engine.connect() as connection:
        rows = (await connection.execute(sa.select(template))).all()
    assert len(rows) == 21
    assert sum(row.kind == "EXPENSE" for row in rows) == 16
    assert sum(row.kind == "INCOME" for row in rows) == 5
    assert all(row.name_ru and row.name_en for row in rows)
    downgrade(revision="0005")
    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda sync: sa.inspect(sync).get_table_names())
    assert "finance_template_category" not in tables


async def test_finance_category_delete_preserves_uncategorized_transaction_history(
    engine: AsyncEngine,
    migrated_to_0005: None,
) -> None:
    _ = migrated_to_0005
    migrate(revision="0006")
    metadata = sa.MetaData()
    now = datetime(2026, 9, 15, 12, tzinfo=UTC)
    async with engine.begin() as connection:
        await connection.run_sync(metadata.reflect)
        tracker = metadata.tables["finance_tracker"]
        month = metadata.tables["finance_month"]
        category = metadata.tables["finance_category"]
        snapshot = metadata.tables["finance_month_category"]
        rate_set = metadata.tables["finance_rate_set"]
        transaction = metadata.tables["finance_transaction"]
        revision = metadata.tables["finance_transaction_revision"]
        await connection.execute(
            tracker.insert().values(
                id="tracker",
                owner_username="owner",
                timezone_name="UTC",
                created_at=now,
            ),
        )
        await connection.execute(
            month.insert().values(
                id="september",
                tracker_id="tracker",
                period_start=date(2026, 9, 1),
                currency="USD",
                opening_balance=Decimal(0),
                previous_month_id=None,
                transferred_balance=None,
                version=1,
                created_at=now,
            ),
        )
        await connection.execute(
            category.insert().values(
                id="category",
                tracker_id="tracker",
                kind="EXPENSE",
                archived_at=None,
                created_at=now,
            ),
        )
        await connection.execute(
            snapshot.insert().values(
                id="september-category",
                month_id="september",
                category_id="category",
                kind="EXPENSE",
                name="Food",
                normalized_name="food",
                planned_amount=None,
                position=0,
                accepting_transactions=True,
                source_month_category_id=None,
            ),
        )
        await connection.execute(
            month.insert().values(
                id="october",
                tracker_id="tracker",
                period_start=date(2026, 10, 1),
                currency="USD",
                opening_balance=Decimal(-10),
                previous_month_id="september",
                transferred_balance=Decimal(-10),
                version=1,
                created_at=now,
            ),
        )
        await connection.execute(
            snapshot.insert().values(
                id="october-category",
                month_id="october",
                category_id="category",
                kind="EXPENSE",
                name="Groceries",
                normalized_name="groceries",
                planned_amount=None,
                position=0,
                accepting_transactions=True,
                source_month_category_id="september-category",
            ),
        )
        await connection.execute(
            rate_set.insert().values(
                id="rates",
                provider="cbr",
                effective_on=now.date(),
                fetched_at=now,
                payload_hash="hash",
            ),
        )
        await connection.execute(
            transaction.insert().values(
                id="transaction",
                month_id="september",
                month_category_id="september-category",
                kind="EXPENSE",
                original_amount=Decimal(10),
                original_currency="USD",
                amount_rub=Decimal(800),
                rate_set_id="rates",
                occurred_at=now,
                description="Meal",
                author_username="owner",
                version=2,
                deleted_at=None,
                created_at=now,
                updated_at=now,
            ),
        )
        previous_state = {"categoryId": "september-category", "amount": "5", "kind": "expense"}
        await connection.execute(
            revision.insert().values(
                id="revision",
                transaction_id="transaction",
                number=1,
                action="UPDATE",
                previous_state=previous_state,
                actor_username="owner",
                changed_at=now,
            ),
        )
        await connection.execute(category.delete().where(category.c.id == "category"))
        assert await connection.scalar(sa.select(sa.func.count()).select_from(snapshot)) == 0
        row = (await connection.execute(sa.select(transaction))).one()
        assert row.month_category_id is None
        assert row.kind == "EXPENSE"
        assert (row.original_amount, row.amount_rub, row.version, row.occurred_at) == (
            Decimal(10),
            Decimal(800),
            2,
            now,
        )
        assert await connection.scalar(sa.select(revision.c.previous_state)) == previous_state
    downgrade(revision="0005")
