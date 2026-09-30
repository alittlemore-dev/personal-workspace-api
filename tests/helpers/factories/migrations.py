from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceMigrationRows:
    expected_rows: dict[str, dict[str, object]]
    revision_snapshot: dict[str, str | int | bool]
    template_rows: list[dict[str, object]]


class MigrationFactoryHelper:
    @classmethod
    def finance_previous_schema(cls, connection: Connection, legacy_schema: bool) -> None:
        if not legacy_schema:
            return
        operations = Operations(MigrationContext.configure(connection))
        operations.drop_column("finance_transaction", "kind")
        operations.alter_column("finance_transaction", "month_category_id", nullable=False)
        for table_name, column_name, target_table in (
            ("finance_month_category", "category_id", "finance_category"),
            ("finance_month_category", "source_month_category_id", "finance_month_category"),
            ("finance_transaction", "month_category_id", "finance_month_category"),
        ):
            constraint_name = f"{table_name}_{column_name}_fkey"
            operations.drop_constraint(constraint_name, table_name, type_="foreignkey")
            operations.create_foreign_key(
                constraint_name,
                table_name,
                target_table,
                [column_name],
                ["id"],
            )

    @classmethod
    async def finance_rows(
        cls,
        connection: AsyncConnection,
        legacy_schema: bool,
    ) -> FinanceMigrationRows:
        now = datetime(2026, 9, 15, 12, tzinfo=UTC)
        snapshot: dict[str, str | int | bool] = {
            "categoryId": "category-snapshot",
            "kind": "expense",
            "amount": "10",
            "currency": "USD",
            "amountRub": "800",
            "rateSetId": "rates",
            "occurredAt": now.isoformat(),
            "description": "Meal",
            "version": 1,
            "deleted": False,
        }
        inserted: dict[str, dict[str, object]] = {
            "finance_tracker": {
                "id": "tracker",
                "owner_username": "owner",
                "timezone_name": "Asia/Yerevan",
                "created_at": now,
            },
            "finance_month": {
                "id": "month",
                "tracker_id": "tracker",
                "period_start": date(2026, 9, 1),
                "currency": "USD",
                "opening_balance": Decimal(100),
                "previous_month_id": None,
                "transferred_balance": None,
                "version": 2,
                "created_at": now,
            },
            "finance_category": {
                "id": "category",
                "tracker_id": "tracker",
                "kind": "EXPENSE",
                "archived_at": None,
                "created_at": now,
            },
            "finance_month_category": {
                "id": "category-snapshot",
                "month_id": "month",
                "category_id": "category",
                "kind": "EXPENSE",
                "name": "Food",
                "normalized_name": "food",
                "planned_amount": Decimal(50),
                "position": 0,
                "accepting_transactions": True,
                "source_month_category_id": None,
            },
            "finance_rate_set": {
                "id": "rates",
                "provider": "cbr",
                "effective_on": now.date(),
                "fetched_at": now,
                "payload_hash": "hash",
            },
            "finance_rate": {
                "rate_set_id": "rates",
                "currency": "USD",
                "nominal": 1,
                "rub_per_unit": Decimal(80),
            },
            "finance_transaction": {
                "id": "transaction",
                "month_id": "month",
                "month_category_id": "category-snapshot",
                "kind": "EXPENSE",
                "original_amount": Decimal(10),
                "original_currency": "USD",
                "amount_rub": Decimal(800),
                "rate_set_id": "rates",
                "occurred_at": now,
                "description": "Meal",
                "author_username": "owner",
                "version": 2,
                "deleted_at": None,
                "created_at": now,
                "updated_at": now,
            },
            "finance_transaction_revision": {
                "id": "revision",
                "transaction_id": "transaction",
                "number": 1,
                "action": "UPDATE",
                "previous_state": snapshot,
                "actor_username": "owner",
                "changed_at": now,
            },
            "finance_month_currency_change": {
                "id": "currency-change",
                "month_id": "month",
                "previous_currency": "RUB",
                "new_currency": "USD",
                "rate_set_id": "rates",
                "before_state": {"openingBalance": "8000", "plans": {"category-snapshot": "4000"}},
                "after_state": {"openingBalance": "100", "plans": {"category-snapshot": "50"}},
                "actor_username": "owner",
                "changed_at": now,
            },
        }
        metadata = sa.MetaData()
        await connection.run_sync(metadata.reflect)
        for table_name, values in inserted.items():
            original_values = values.copy()
            if legacy_schema and table_name == "finance_transaction":
                original_values.pop("kind")
            if legacy_schema and table_name == "finance_transaction_revision":
                original_values["previous_state"] = {
                    key: value for key, value in snapshot.items() if key != "kind"
                }
            await connection.execute(metadata.tables[table_name].insert().values(**original_values))
        if legacy_schema:
            await connection.execute(
                metadata.tables["finance_category"]
                .insert()
                .values(
                    id="new-category",
                    tracker_id="tracker",
                    kind="INCOME",
                    archived_at=None,
                    created_at=now,
                ),
            )
            await connection.execute(
                metadata.tables["finance_month_category"]
                .insert()
                .values(
                    id="new-category-snapshot",
                    month_id="month",
                    category_id="new-category",
                    kind="INCOME",
                    name="Salary",
                    normalized_name="salary",
                    planned_amount=None,
                    position=0,
                    accepting_transactions=True,
                    source_month_category_id=None,
                ),
            )
            original_transaction = metadata.tables["finance_transaction"]
            await connection.execute(
                original_transaction.update()
                .where(original_transaction.c.id == "transaction")
                .values(month_category_id="new-category-snapshot"),
            )
            inserted["finance_transaction"]["month_category_id"] = "new-category-snapshot"
            inserted["finance_transaction"]["kind"] = "INCOME"
        template_rows = (
            (await connection.execute(sa.select(metadata.tables["finance_template_category"])))
            .mappings()
            .all()
        )

        return FinanceMigrationRows(
            expected_rows=inserted,
            revision_snapshot=snapshot,
            template_rows=[dict(row) for row in template_rows],
        )
