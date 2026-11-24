from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alembic has no typed operation to add values to an existing PostgreSQL enum.
    for label in ("DEPOSIT_EXTERNAL", "WITHDRAW_EXTERNAL"):
        op.execute(sa.text(f"ALTER TYPE asset_movement_kind_enum ADD VALUE IF NOT EXISTS '{label}'"))
    op.add_column(
        "finance_assets__asset_position_model",
        sa.Column("archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "finance_assets__asset_position_model",
        sa.Column("creation_request_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "finance_assets__asset_position_model",
        sa.Column("creation_signature", sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint(
        "asset_position_creation_request_uq", "finance_assets__asset_position_model", ["tracker_id", "creation_request_id"]
    )


def downgrade() -> None:
    # Earlier readers deserialize the full revision, including cancelled or corrected movements.
    revisions = sa.table(
        "finance_assets__asset_movement_revision_model",
        sa.column("snapshot", postgresql.JSONB()),
    )
    external = revisions.c.snapshot[("value", "draft", "kind")].astext.in_(
        ("depositExternal", "withdrawExternal"),
    )
    if op.get_bind().scalar(sa.select(sa.exists().where(external))):
        raise RuntimeError("Cannot downgrade while external asset movements exist in the journal")
    op.drop_constraint("asset_position_creation_request_uq", "finance_assets__asset_position_model", type_="unique")
    op.drop_column("finance_assets__asset_position_model", "creation_signature")
    op.drop_column("finance_assets__asset_position_model", "creation_request_id")
    op.drop_column("finance_assets__asset_position_model", "archived")
