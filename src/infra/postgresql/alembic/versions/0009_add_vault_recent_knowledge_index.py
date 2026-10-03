from alembic import op
import sqlalchemy as sa


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "knowledge_items_author_updated_id_idx",
        "knowledge__knowledge_item_model",
        ["author_username", sa.column("updated_at").desc(), sa.column("id").desc()],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "knowledge_items_author_updated_id_idx", table_name="knowledge__knowledge_item_model"
    )
