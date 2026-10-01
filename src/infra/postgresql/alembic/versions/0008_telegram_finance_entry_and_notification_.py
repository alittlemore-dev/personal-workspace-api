import sqlalchemy as sa
import sqlalchemy_dev_utils.types.datetime
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    event_enum = postgresql.ENUM(
        "TRANSACTION",
        "LIMIT",
        name="finance_event_kind_enum",
        create_type=False,
    )
    event_enum.create(bind, checkfirst=True)
    source_enum = postgresql.ENUM("WEB", "TELEGRAM", name="finance_source_enum", create_type=False)
    source_enum.create(bind, checkfirst=True)
    op.create_table(
        "finance_notifications__finance_event_model",
        sa.Column("owner_username", sa.String(length=255), nullable=False),
        sa.Column(
            "kind",
            event_enum,
            nullable=False,
        ),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sqlalchemy_dev_utils.types.datetime.UTCDateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sqlalchemy_dev_utils.types.datetime.UTCDateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "planned_at",
            sqlalchemy_dev_utils.types.datetime.UTCDateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "id",
            sa.String(length=32),
            server_default=sa.text("replace(CAST(gen_random_uuid() AS VARCHAR), '-', '')"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_finance_notifications__finance_event_model_owner_username"),
        "finance_notifications__finance_event_model",
        ["owner_username"],
        unique=False,
    )
    op.create_table(
        "finance_notifications__finance_delivery_model",
        sa.Column("event_id", sa.String(length=32), nullable=False),
        sa.Column("connection_id", sa.String(length=32), nullable=False),
        sa.Column(
            "kind",
            event_enum,
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PENDING",
                "IN_PROGRESS",
                "RETRY",
                "DONE",
                "CANCELED",
                "EXPIRED",
                "FAILED",
                name="reminder_delivery_status_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column(
            "claimed_until",
            sqlalchemy_dev_utils.types.datetime.UTCDateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "next_attempt_at",
            sqlalchemy_dev_utils.types.datetime.UTCDateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sqlalchemy_dev_utils.types.datetime.UTCDateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "id",
            sa.String(length=32),
            server_default=sa.text("replace(CAST(gen_random_uuid() AS VARCHAR), '-', '')"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["finance_notifications__finance_event_model.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "connection_id", "kind", name="finance_delivery_once"),
    )
    op.create_index(
        "finance_delivery_due_idx",
        "finance_notifications__finance_delivery_model",
        ["status", "next_attempt_at"],
        unique=False,
    )
    op.add_column(
        "finance__finance_transaction_model",
        sa.Column("source", source_enum, nullable=True),
    )
    op.add_column(
        "finance__finance_transaction_model",
        sa.Column("author_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "finance__finance_transaction_model",
        sa.Column("author_label", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "finance__finance_transaction_model",
        sa.Column("operation_id", sa.String(length=32), nullable=True),
    )
    transactions = sa.table(
        "finance__finance_transaction_model",
        sa.column("source", source_enum),
        sa.column("author_username", sa.String()),
        sa.column("author_id", sa.String()),
        sa.column("author_label", sa.String()),
        sa.column("operation_id", sa.String()),
    )
    bind.execute(
        transactions.update().values(
            source="WEB",
            author_id=transactions.c.author_username,
            author_label=transactions.c.author_username,
            operation_id="",
        ),
    )
    for column in ("source", "author_id", "author_label", "operation_id"):
        op.alter_column("finance__finance_transaction_model", column, nullable=False)
    op.create_index(
        "finance_telegram_operation_once",
        "finance__finance_transaction_model",
        ["operation_id"],
        unique=True,
        postgresql_where=sa.column("source", source_enum) == "TELEGRAM",
    )
    op.add_column(
        "telegram__telegram_connection_model",
        sa.Column("notify_finance_transaction", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "telegram__telegram_connection_model",
        sa.Column("notify_finance_limit", sa.Boolean(), nullable=True),
    )
    connections = sa.table(
        "telegram__telegram_connection_model",
        sa.column("notify_finance_transaction", sa.Boolean()),
        sa.column("notify_finance_limit", sa.Boolean()),
    )
    bind.execute(
        connections.update().values(notify_finance_transaction=False, notify_finance_limit=False),
    )
    op.alter_column(
        "telegram__telegram_connection_model",
        "notify_finance_transaction",
        nullable=False,
    )
    op.alter_column("telegram__telegram_connection_model", "notify_finance_limit", nullable=False)


def downgrade() -> None:
    op.drop_column("telegram__telegram_connection_model", "notify_finance_limit")
    op.drop_column("telegram__telegram_connection_model", "notify_finance_transaction")
    op.drop_index(
        "finance_telegram_operation_once",
        table_name="finance__finance_transaction_model",
    )
    op.drop_column("finance__finance_transaction_model", "operation_id")
    op.drop_column("finance__finance_transaction_model", "author_label")
    op.drop_column("finance__finance_transaction_model", "author_id")
    op.drop_column("finance__finance_transaction_model", "source")
    op.drop_index(
        "finance_delivery_due_idx",
        table_name="finance_notifications__finance_delivery_model",
    )
    op.drop_table("finance_notifications__finance_delivery_model")
    op.drop_index(
        op.f("ix_finance_notifications__finance_event_model_owner_username"),
        table_name="finance_notifications__finance_event_model",
    )
    op.drop_table("finance_notifications__finance_event_model")

    postgresql.ENUM(name="finance_event_kind_enum").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="finance_source_enum").drop(op.get_bind(), checkfirst=True)
