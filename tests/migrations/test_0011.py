from collections.abc import Generator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from infra.postgresql.utils import downgrade, migrate


@pytest.fixture
def before_resume_sections() -> Generator[None]:
    migrate(revision="0010")
    yield
    downgrade(revision="base")


async def test_resume_sections_upgrade_preserves_content_and_explicit_preferences(
    engine: AsyncEngine,
    before_resume_sections: None,
) -> None:
    _ = before_resume_sections
    metadata = sa.MetaData()
    existing_contents: dict[str, dict[str, object]] = {
        "a" * 32: {
            "profile": {"full_name": "Legacy candidate"},
            "settings": {"date_format": "year"},
        },
        "b" * 32: {
            "profile": {"full_name": "Configured candidate"},
            "settings": {
                "date_format": "fullDate",
                "section_order": [
                    "additionalSections",
                    "certifications",
                    "languages",
                    "education",
                    "experience",
                    "skills",
                    "summary",
                ],
                "hidden_sections": ["summary"],
            },
        },
        "c" * 32: {
            "settings": {"date_format": "monthYear", "hidden_sections": ["education"]},
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
                    language="EN",
                    author_username="owner",
                    content=content,
                    created_at=datetime(2026, 9, 1, tzinfo=UTC),
                    updated_at=datetime(2026, 9, 2, tzinfo=UTC),
                ),
            )
    migrate(revision="0011")
    async with engine.begin() as connection:
        upgraded = {
            row.id: row.content
            for row in (await connection.execute(sa.select(table.c.id, table.c.content))).all()
        }
    assert upgraded == {
        "a" * 32: {
            **existing_contents["a" * 32],
            "settings": {"date_format": "year", "section_order": [], "hidden_sections": []},
        },
        "b" * 32: existing_contents["b" * 32],
        "c" * 32: {
            "settings": {
                "date_format": "monthYear",
                "section_order": [],
                "hidden_sections": ["education"],
            },
        },
    }
    downgrade(revision="0010")
    async with engine.begin() as connection:
        downgraded = {
            row.id: row.content
            for row in (await connection.execute(sa.select(table.c.id, table.c.content))).all()
        }
    assert downgraded == upgraded
