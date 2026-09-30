import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

TABLE_RENAMES = (
    ("finance_template_category", "finance__finance_template_category_model"),
    ("finance_tracker", "finance__finance_tracker_model"),
    ("finance_month", "finance__finance_month_model"),
    ("finance_category", "finance__finance_category_model"),
    ("finance_month_category", "finance__finance_month_category_model"),
    ("finance_rate_set", "finance__finance_rate_set_model"),
    ("finance_rate", "finance__finance_rate_model"),
    ("finance_transaction", "finance__finance_transaction_model"),
    ("finance_transaction_revision", "finance__finance_transaction_revision_model"),
    ("finance_month_currency_change", "finance__finance_month_currency_change_model"),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    transaction_columns = inspector.get_columns("finance_transaction")
    kind_type = postgresql.ENUM(
        "INCOME",
        "EXPENSE",
        name="finance_kind_enum",
        create_type=False,
    )
    # Some local databases applied 0006 before its category-deletion correction.
    if not any(column["name"] == "kind" for column in transaction_columns):
        op.add_column("finance_transaction", sa.Column("kind", kind_type, nullable=True))
    transaction = sa.table(
        "finance_transaction",
        sa.column("id", sa.String(32)),
        sa.column("month_category_id", sa.String(32)),
        sa.column("kind", kind_type),
    )
    category = sa.table(
        "finance_month_category",
        sa.column("id", sa.String(32)),
        sa.column("kind", kind_type),
    )
    op.execute(
        transaction.update()
        .where(
            transaction.c.kind.is_(None),
            transaction.c.month_category_id == category.c.id,
        )
        .values(kind=category.c.kind),
    )
    op.alter_column("finance_transaction", "kind", existing_type=kind_type, nullable=False)
    op.alter_column(
        "finance_transaction",
        "month_category_id",
        existing_type=sa.String(32),
        nullable=True,
    )
    for table_name, column_name, target_table, ondelete in (
        ("finance_month_category", "category_id", "finance_category", "CASCADE"),
        (
            "finance_month_category",
            "source_month_category_id",
            "finance_month_category",
            "SET NULL",
        ),
        ("finance_transaction", "month_category_id", "finance_month_category", "SET NULL"),
    ):
        constraint = next(
            foreign_key
            for foreign_key in inspector.get_foreign_keys(table_name)
            if foreign_key["constrained_columns"] == [column_name]
        )
        if constraint["options"].get("ondelete") == ondelete:
            continue
        constraint_name = constraint["name"]
        if constraint_name is None:
            message = "PostgreSQL finance foreign key must have a name"
            raise ValueError(message)
        op.drop_constraint(constraint_name, table_name, type_="foreignkey")
        op.create_foreign_key(
            constraint_name,
            table_name,
            target_table,
            [column_name],
            ["id"],
            ondelete=ondelete,
        )
    revision_table = sa.table(
        "finance_transaction_revision",
        sa.column("transaction_id", sa.String(32)),
        sa.column("previous_state", postgresql.JSONB()),
    )
    previous_kind = (
        sa.select(category.c.kind)
        .where(category.c.id == revision_table.c.previous_state["categoryId"].astext)
        .scalar_subquery()
    )
    transaction_kind = (
        sa.select(transaction.c.kind)
        .where(transaction.c.id == revision_table.c.transaction_id)
        .scalar_subquery()
    )
    op.execute(
        revision_table.update()
        .where(revision_table.c.previous_state["kind"].astext.is_(None))
        .values(
            previous_state=revision_table.c.previous_state.op("||")(
                sa.func.jsonb_build_object(
                    "kind",
                    sa.func.lower(
                        sa.cast(sa.func.coalesce(previous_kind, transaction_kind), sa.String()),
                    ),
                ),
            ),
        ),
    )
    # Renames preserve populated tables, JSONB snapshots, indexes and foreign-key relationships.
    for previous_name, model_name in TABLE_RENAMES:
        op.rename_table(previous_name, model_name)


def downgrade() -> None:
    # Keep the corrected 0006 data contract; category-less transactions cannot regain NOT NULL.
    for previous_name, model_name in reversed(TABLE_RENAMES):
        op.rename_table(model_name, previous_name)
