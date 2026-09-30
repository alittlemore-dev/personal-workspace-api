from collections.abc import Generator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from infra.postgresql.utils import downgrade, migrate
from tests.helpers.factories.migrations import MigrationFactoryHelper


@pytest.fixture
def migrated_to_0006() -> Generator[None]:
    migrate(revision="0006")
    yield
    downgrade(revision="base")


@pytest.mark.parametrize("legacy_schema", [False, True])
async def test_finance_table_renames_preserve_data_and_relations_in_both_directions(
    engine: AsyncEngine,
    migrated_to_0006: None,
    legacy_schema: bool,
) -> None:
    _ = migrated_to_0006
    factory = MigrationFactoryHelper()
    async with engine.begin() as connection:
        await connection.run_sync(factory.finance_previous_schema, legacy_schema)
        rows = await factory.finance_rows(connection, legacy_schema)
    inserted = rows.expected_rows
    snapshot = rows.revision_snapshot
    template_rows = rows.template_rows

    migrate(revision="0007")
    upgraded = sa.MetaData()
    async with engine.begin() as connection:
        await connection.run_sync(upgraded.reflect)
        for table_name, values in inserted.items():
            new_name = f"finance__{table_name}_model"
            assert table_name not in upgraded.tables
            table = upgraded.tables[new_name]
            query = sa.select(table)
            if "id" in values:
                query = query.where(table.c.id == values["id"])
            row = (await connection.execute(query)).mappings().one()
            assert dict(row) == values
        renamed_template = upgraded.tables["finance__finance_template_category_model"]
        assert [
            dict(row) for row in (await connection.execute(sa.select(renamed_template))).mappings()
        ] == template_rows
        transaction = upgraded.tables["finance__finance_transaction_model"]
        assert transaction.c.month_id.references(
            upgraded.tables["finance__finance_month_model"].c.id,
        )
        await connection.execute(
            upgraded.tables["finance__finance_category_model"]
            .delete()
            .where(
                upgraded.tables["finance__finance_category_model"].c.id.in_(
                    ["category", "new-category"],
                ),
            ),
        )
        assert await connection.scalar(sa.select(transaction.c.month_category_id)) is None
        assert (
            await connection.scalar(
                sa.select(
                    upgraded.tables["finance__finance_transaction_revision_model"].c.previous_state,
                ),
            )
            == snapshot
        )

    downgrade(revision="0006")
    downgraded = sa.MetaData()
    async with engine.connect() as connection:
        await connection.run_sync(downgraded.reflect)
        for table_name, original_values in inserted.items():
            assert f"finance__{table_name}_model" not in downgraded.tables
            if table_name in {"finance_category", "finance_month_category"}:
                assert (
                    await connection.scalar(
                        sa.select(sa.func.count()).select_from(downgraded.tables[table_name]),
                    )
                    == 0
                )
                continue
            values = original_values.copy()
            if table_name == "finance_transaction":
                values["month_category_id"] = None
            row = (
                (await connection.execute(sa.select(downgraded.tables[table_name])))
                .mappings()
                .one()
            )
            assert dict(row) == values
        assert [
            dict(row)
            for row in (
                await connection.execute(sa.select(downgraded.tables["finance_template_category"]))
            ).mappings()
        ] == template_rows
