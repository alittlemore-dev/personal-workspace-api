from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    resumes = sa.table("resumes__resume_model", sa.column("content", JSONB()))
    settings = resumes.c.content["settings"]
    for key in ("section_order", "hidden_sections"):
        op.execute(
            sa.update(resumes)
            .where(~settings.has_key(key))
            .values(
                content=sa.func.jsonb_set(
                    resumes.c.content,
                    sa.literal(["settings"], type_=sa.ARRAY(sa.Text())),
                    settings.concat(sa.literal({key: []}, type_=JSONB())),
                ),
            ),
        )


def downgrade() -> None:
    # Older readers ignore the lists; retaining them preserves explicitly chosen preferences.
    pass
