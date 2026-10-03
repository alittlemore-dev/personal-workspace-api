from collections.abc import Generator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from infra.postgresql.utils import downgrade, migrate


@pytest.fixture
def before_resume_settings() -> Generator[None]:
    migrate(revision="0009")
    yield
    downgrade(revision="base")


async def test_resume_settings_upgrade_preserves_existing_content_and_date_formats(
    engine: AsyncEngine,
    before_resume_settings: None,
) -> None:
    _ = before_resume_settings
    metadata = sa.MetaData()
    existing_contents = {
        "a" * 32: {"profile": {"full_name": "Russian candidate"}},
        "b" * 32: {"profile": {"full_name": "English candidate"}},
        "c" * 32: {
            "profile": {"full_name": "Configured candidate"},
            "settings": {"date_format": "fullDate"},
        },
    }
    async with engine.begin() as connection:
        await connection.run_sync(metadata.reflect)
        table = metadata.tables["resumes__resume_model"]
        for resume_id, content in existing_contents.items():
            await connection.execute(
                sa.insert(table).values(
                    id=resume_id,
                    title="Resume",
                    language="EN" if resume_id.startswith("b") else "RU",
                    author_username="owner",
                    content=content,
                    created_at=datetime(2026, 9, 1, tzinfo=UTC),
                    updated_at=datetime(2026, 9, 2, tzinfo=UTC),
                ),
            )
    migrate(revision="0010")
    async with engine.begin() as connection:
        upgraded: dict[str, object] = {
            row.id: row.content
            for row in (await connection.execute(sa.select(table.c.id, table.c.content))).all()
        }
    assert upgraded == {
        "a" * 32: {**existing_contents["a" * 32], "settings": {"date_format": "monthYearNumeric"}},
        "b" * 32: {**existing_contents["b" * 32], "settings": {"date_format": "monthYear"}},
        "c" * 32: existing_contents["c" * 32],
    }
    downgrade(revision="0009")
    async with engine.begin() as connection:
        downgraded: dict[str, object] = {
            row.id: row.content
            for row in (await connection.execute(sa.select(table.c.id, table.c.content))).all()
        }
    assert downgraded == upgraded
