from collections.abc import Generator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from infra.postgresql.utils import downgrade, migrate

POSITION_TABLE = "finance_assets__asset_position_model"
MOVEMENT_TABLE = "finance_assets__asset_movement_model"


@pytest.fixture
def before_position_lifecycle() -> Generator[None]:
    migrate(revision="0012")
    yield
    downgrade(revision="base")


@pytest_asyncio.fixture
async def legacy_balance(
    engine: AsyncEngine,
    before_position_lifecycle: None,
) -> None:
    _ = before_position_lifecycle
    now = datetime(2026, 3, 15, tzinfo=UTC)
    old = sa.MetaData()
    async with engine.begin() as conn:
        await conn.run_sync(old.reflect)
        await conn.execute(
            old.tables["finance__finance_tracker_model"]
            .insert()
            .values(
                id="t",
                owner_username="owner",
                timezone_name="UTC",
                created_at=now,
            ),
        )
        await conn.execute(
            old.tables["finance_assets__asset_location_model"]
            .insert()
            .values(
                id="bank",
                tracker_id="t",
                name="Bank",
            ),
        )
        await conn.execute(
            old.tables[POSITION_TABLE]
            .insert()
            .values(
                id="account",
                tracker_id="t",
                location_id="bank",
                name="Savings",
                kind="SAVINGS",
                currency="RUB",
                instrument="",
                venue="",
            ),
        )
        await conn.execute(
            old.tables[MOVEMENT_TABLE]
            .insert()
            .values(
                id="first",
                tracker_id="t",
                request_id=uuid4(),
                position_id="account",
                on_date=now.date(),
                kind="RECONCILE",
                source="WEB",
                version=1,
                deleted=False,
                created_at=now,
                changed_at=now,
                draft={
                    "value": {
                        "kind": "reconcile",
                        "on_date": now.date().isoformat(),
                        "position_id": "account",
                        "amount": "12000",
                        "counter_position_id": None,
                        "quantity": None,
                        "total_value": None,
                        "counter_amount": None,
                        "category_id": None,
                        "note": "",
                    },
                },
            ),
        )


async def test_existing_asset_and_balance_survive_lifecycle_upgrade_and_downgrade(
    engine: AsyncEngine,
    legacy_balance: None,
) -> None:
    _ = legacy_balance
    migrate(revision="0013")
    current = sa.MetaData()
    async with engine.begin() as conn:
        await conn.run_sync(current.reflect)
        position = current.tables[POSITION_TABLE]
        values = await conn.execute(
            sa.select(position.c.name, position.c.archived, position.c.creation_request_id),
        )
        assert values.one() == ("Savings", False, None)
        movement = current.tables[MOVEMENT_TABLE]
        result = (await conn.execute(sa.select(movement.c.position_id, movement.c.draft))).one()
        assert result.position_id == "account"
        assert result.draft["value"]["amount"] == "12000"
    downgrade(revision="0012")
    downgraded = sa.MetaData()
    async with engine.begin() as conn:
        await conn.run_sync(downgraded.reflect)
        assert "archived" not in downgraded.tables[POSITION_TABLE].c
        assert await conn.scalar(sa.select(downgraded.tables[POSITION_TABLE].c.name)) == "Savings"
        remaining = await conn.scalar(sa.select(downgraded.tables[MOVEMENT_TABLE].c.draft))
        assert remaining is not None
        assert remaining["value"]["amount"] == "12000"


@pytest.mark.parametrize("corrected", [False, True])
async def test_downgrade_refuses_external_movements_in_live_and_corrected_history(
    engine: AsyncEngine,
    legacy_balance: None,
    *,
    corrected: bool,
) -> None:
    _ = legacy_balance
    migrate(revision="0013")
    meta = sa.MetaData()
    async with engine.begin() as conn:
        await conn.run_sync(meta.reflect)
        rows = meta.tables[MOVEMENT_TABLE]
        revisions = meta.tables["finance_assets__asset_movement_revision_model"]
        row = (await conn.execute(sa.select(rows))).mappings().one()
        external_draft = {**row["draft"]["value"], "kind": "depositExternal"}
        snapshot = {
            "id": row["id"],
            "request_id": str(row["request_id"]),
            "source": "web",
            "version": 1,
            "draft": external_draft,
            "deleted": False,
            "transaction_id": None,
            "rate_set_id": None,
            "created_at": row["created_at"].isoformat(),
            "changed_at": row["changed_at"].isoformat(),
        }
        await conn.execute(
            revisions.insert().values(
                movement_id=row["id"],
                version=1,
                snapshot={"value": snapshot},
            ),
        )
        if corrected:
            await conn.execute(rows.update().values(version=2))
            await conn.execute(
                revisions.insert().values(
                    movement_id=row["id"],
                    version=2,
                    snapshot={"value": {**snapshot, "version": 2, "draft": row["draft"]["value"]}},
                ),
            )
        else:
            await conn.execute(
                rows.update().values(kind="DEPOSIT_EXTERNAL", draft={"value": external_draft}),
            )
    try:
        with pytest.raises(RuntimeError, match="downgrade"):
            downgrade(revision="0012")
        async with engine.begin() as conn:
            assert await conn.scalar(sa.select(sa.func.count()).select_from(revisions)) == (
                2 if corrected else 1
            )
            assert await conn.scalar(sa.select(meta.tables[POSITION_TABLE].c.archived)) is False
    finally:
        async with engine.begin() as conn:
            await conn.execute(rows.delete())
