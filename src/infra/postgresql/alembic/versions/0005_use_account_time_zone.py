from alembic import op
import sqlalchemy as sa
from sqlalchemy_dev_utils.types.datetime import UTCDateTime


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notifications__reminder_delivery_model",
        sa.Column("scheduled_at", UTCDateTime(timezone=True), nullable=False),
    )
    op.drop_column("telegram__telegram_connection_model", "time_zone")


def downgrade() -> None:
    op.add_column(
        "telegram__telegram_connection_model",
        sa.Column("time_zone", sa.String(length=64), server_default="UTC", nullable=False),
    )
    op.drop_column("notifications__reminder_delivery_model", "scheduled_at")
