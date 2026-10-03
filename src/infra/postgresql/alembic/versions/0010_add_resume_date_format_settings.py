from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    resumes = sa.table(
        "resumes__resume_model",
        sa.column("language", sa.Enum("RU", "EN", name="language_enum")),
        sa.column("content", JSONB()),
    )
    for language, date_format in (("RU", "monthYearNumeric"), ("EN", "monthYear")):
        op.execute(
            sa.update(resumes)
            .where(resumes.c.language == language, ~resumes.c.content.has_key("settings"))
            .values(
                content=resumes.c.content.concat(
                    sa.literal({"settings": {"date_format": date_format}}, type_=JSONB()),
                ),
            ),
        )


def downgrade() -> None:
    # Older readers ignore settings; retaining them preserves explicitly chosen preferences.
    pass
