from alembic import op
import sqlalchemy as sa
from sqlalchemy_dev_utils.types.datetime import UTCDateTime


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_model",
        sa.Column("author_username", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("anchor_time_zone", sa.String(length=255), nullable=False),
        sa.Column("all_day", sa.Boolean(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column(
            "start_at",
            UTCDateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "end_at", UTCDateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "frequency",
            sa.Enum("none", "daily", "weekly", "monthly", "yearly", name="event_frequency_enum"),
            nullable=False,
        ),
        sa.Column("until_date", sa.Date(), nullable=True),
        sa.Column(
            "id",
            sa.String(length=32),
            server_default=sa.text("replace(CAST(gen_random_uuid() AS VARCHAR), '-', '')"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "event_author_start_idx",
        "event_model",
        ["author_username", "start_at", "start_date"],
        unique=False,
    )
    op.create_table(
        "important_info_model",
        sa.Column("author_username", sa.String(length=255), nullable=False),
        sa.Column("text", sa.String(length=255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "id",
            sa.String(length=32),
            server_default=sa.text("replace(CAST(gen_random_uuid() AS VARCHAR), '-', '')"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "important_info_author_position_id_idx",
        "important_info_model",
        ["author_username", "position", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("important_info_author_position_id_idx", table_name="important_info_model")
    op.drop_table("important_info_model")
    op.drop_index("event_author_start_idx", table_name="event_model")
    op.drop_table("event_model")
    sa.Enum(name="event_frequency_enum").drop(op.get_bind(), checkfirst=True)
