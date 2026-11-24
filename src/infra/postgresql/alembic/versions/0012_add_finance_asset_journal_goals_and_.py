from alembic import op
import sqlalchemy as sa
import sqlalchemy_dev_utils.types.datetime
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL cannot extend an existing enum through Alembic's typed column operations.
    for label in ("ASSET_MOVEMENT", "SAVINGS_GOAL", "MONTH_SUMMARY", "DEPOSIT_MATURITY"):
        op.execute(sa.text(f"ALTER TYPE finance_event_kind_enum ADD VALUE IF NOT EXISTS '{label}'"))

    op.create_table(
        "finance_asset_analytics__asset_goal_model",
        sa.Column("owner_username", sa.String(length=255), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("percent", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("all_income", sa.Boolean(), nullable=False),
        sa.Column("category_ids", postgresql.ARRAY(sa.String(length=32)), nullable=False),
        sa.PrimaryKeyConstraint("owner_username", "month"),
    )
    op.create_table(
        "finance_assets__asset_location_model",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("tracker_id", sa.String(length=32), nullable=False),
        sa.Column(
            "id",
            sa.String(length=32),
            server_default=sa.text("replace(CAST(gen_random_uuid() AS VARCHAR), '-', '')"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tracker_id"], ["finance__finance_tracker_model.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_finance_assets__asset_location_model_tracker_id"),
        "finance_assets__asset_location_model",
        ["tracker_id"],
        unique=False,
    )
    op.create_table(
        "finance_assets__asset_position_model",
        sa.Column("location_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "CASH",
                "BANK",
                "BROKER_CASH",
                "SAVINGS",
                "DEPOSIT",
                "STOCK",
                "BOND",
                "FUND",
                "OTHER",
                name="asset_position_kind_enum",
            ),
            nullable=False,
        ),
        sa.Column(
            "currency",
            postgresql.ENUM("AMD", "RUB", "USD", "EUR", name="finance_currency_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("instrument", sa.String(length=255), nullable=False),
        sa.Column("venue", sa.String(length=255), nullable=False),
        sa.Column("annual_rate", sa.Numeric(precision=30, scale=12), nullable=True),
        sa.Column("matures_on", sa.Date(), nullable=True),
        sa.Column("tracker_id", sa.String(length=32), nullable=False),
        sa.Column(
            "id",
            sa.String(length=32),
            server_default=sa.text("replace(CAST(gen_random_uuid() AS VARCHAR), '-', '')"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["location_id"], ["finance_assets__asset_location_model.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tracker_id"], ["finance__finance_tracker_model.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_finance_assets__asset_position_model_tracker_id"),
        "finance_assets__asset_position_model",
        ["tracker_id"],
        unique=False,
    )
    op.create_table(
        "finance_assets__asset_movement_model",
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("position_id", sa.String(length=32), nullable=False),
        sa.Column("counter_position_id", sa.String(length=32), nullable=True),
        sa.Column("on_date", sa.Date(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "OPENING_EXTERNAL",
                "OPENING_BUDGET",
                "STATEMENT",
                "CONTRIBUTION",
                "WITHDRAWAL",
                "TRANSFER",
                "EXCHANGE",
                "BUY",
                "BUY_FROM_BUDGET",
                "SELL",
                "PAYOUT",
                "PAYOUT_TO_BUDGET",
                "FEE",
                "VALUATION",
                "RECONCILE",
                name="asset_movement_kind_enum",
            ),
            nullable=False,
        ),
        sa.Column(
            "source", sa.Enum("WEB", "PAT", name="asset_movement_source_enum"), nullable=False
        ),
        sa.Column("draft", postgresql.JSONB(), nullable=False),
        sa.Column("month_id", sa.String(length=32), nullable=True),
        sa.Column("rate_set_id", sa.String(length=32), nullable=True),
        sa.Column("budget_amount_rub", sa.Numeric(precision=30, scale=12), nullable=True),
        sa.Column("transaction_id", sa.String(length=32), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sqlalchemy_dev_utils.types.datetime.UTCDateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "changed_at",
            sqlalchemy_dev_utils.types.datetime.UTCDateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("tracker_id", sa.String(length=32), nullable=False),
        sa.Column(
            "id",
            sa.String(length=32),
            server_default=sa.text("replace(CAST(gen_random_uuid() AS VARCHAR), '-', '')"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["counter_position_id"],
            ["finance_assets__asset_position_model.id"],
        ),
        sa.ForeignKeyConstraint(
            ["month_id"],
            ["finance__finance_month_model.id"],
        ),
        sa.ForeignKeyConstraint(
            ["position_id"],
            ["finance_assets__asset_position_model.id"],
        ),
        sa.ForeignKeyConstraint(
            ["rate_set_id"],
            ["finance__finance_rate_set_model.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tracker_id"], ["finance__finance_tracker_model.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["finance__finance_transaction_model.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tracker_id", "request_id"),
        sa.UniqueConstraint("transaction_id"),
    )
    op.create_index(
        "asset_movement_month_idx",
        "finance_assets__asset_movement_model",
        ["month_id"],
        unique=False,
    )
    op.create_index(
        "asset_movement_tracker_date_idx",
        "finance_assets__asset_movement_model",
        ["tracker_id", "on_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_finance_assets__asset_movement_model_tracker_id"),
        "finance_assets__asset_movement_model",
        ["tracker_id"],
        unique=False,
    )
    op.create_table(
        "finance_assets__asset_movement_revision_model",
        sa.Column("movement_id", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "id",
            sa.String(length=32),
            server_default=sa.text("replace(CAST(gen_random_uuid() AS VARCHAR), '-', '')"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["movement_id"], ["finance_assets__asset_movement_model.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("movement_id", "version"),
    )
    op.add_column(
        "finance__finance_month_model",
        sa.Column("accepted_transferred_balance", sa.Numeric(precision=30, scale=12), nullable=True),
    )
    op.add_column(
        "finance__finance_transaction_model",
        sa.Column(
            "managed_by_assets", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.add_column(
        "finance__finance_transaction_model",
        sa.Column("former_category_id", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "finance_notifications__finance_event_model",
        sa.Column("source_key", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "finance_notifications__finance_event_model",
        sa.Column("source_active", sa.Boolean(), server_default="true", nullable=False),
    )
    op.create_unique_constraint(
        "finance_event_source_once",
        "finance_notifications__finance_event_model",
        ["owner_username", "kind", "source_key"],
    )
    op.add_column(
        "telegram__telegram_connection_model",
        sa.Column("notify_asset_movement", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "telegram__telegram_connection_model",
        sa.Column(
            "notify_savings_goal_reached", sa.Boolean(), server_default="false", nullable=False
        ),
    )
    op.add_column(
        "telegram__telegram_connection_model",
        sa.Column(
            "notify_assets_month_summary", sa.Boolean(), server_default="false", nullable=False
        ),
    )
    op.add_column(
        "telegram__telegram_connection_model",
        sa.Column("notify_deposit_maturity", sa.Boolean(), server_default="false", nullable=False),
    )



def downgrade() -> None:

    op.drop_column("telegram__telegram_connection_model", "notify_deposit_maturity")
    op.drop_column("telegram__telegram_connection_model", "notify_assets_month_summary")
    op.drop_column("telegram__telegram_connection_model", "notify_savings_goal_reached")
    op.drop_column("telegram__telegram_connection_model", "notify_asset_movement")
    op.drop_constraint(
        "finance_event_source_once", "finance_notifications__finance_event_model", type_="unique"
    )
    op.drop_column("finance_notifications__finance_event_model", "source_active")
    op.drop_column("finance_notifications__finance_event_model", "source_key")
    op.drop_column("finance__finance_transaction_model", "former_category_id")
    op.drop_column("finance__finance_transaction_model", "managed_by_assets")
    op.drop_column("finance__finance_month_model", "accepted_transferred_balance")
    op.drop_table("finance_assets__asset_movement_revision_model")
    op.drop_index(
        op.f("ix_finance_assets__asset_movement_model_tracker_id"),
        table_name="finance_assets__asset_movement_model",
    )
    op.drop_index(
        "asset_movement_tracker_date_idx", table_name="finance_assets__asset_movement_model"
    )
    op.drop_index("asset_movement_month_idx", table_name="finance_assets__asset_movement_model")
    op.drop_table("finance_assets__asset_movement_model")
    op.drop_index(
        op.f("ix_finance_assets__asset_position_model_tracker_id"),
        table_name="finance_assets__asset_position_model",
    )
    op.drop_table("finance_assets__asset_position_model")
    op.drop_index(
        op.f("ix_finance_assets__asset_location_model_tracker_id"),
        table_name="finance_assets__asset_location_model",
    )
    op.drop_table("finance_assets__asset_location_model")
    op.drop_table("finance_asset_analytics__asset_goal_model")

    for name in ("asset_movement_kind_enum", "asset_movement_source_enum", "asset_position_kind_enum"):
        postgresql.ENUM(name=name).drop(op.get_bind())
