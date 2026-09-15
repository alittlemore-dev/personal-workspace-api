from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from core.i18n.enums import LanguageEnum
from core.resumes.enums import ResumeCurrentStatusEnum
from core.resumes.exceptions import ResumeNotFoundError
from core.resumes.schemas import (
    ResumeCreateParams,
    ResumeFilters,
)
from infra.postgresql.models import ResumeModel
from infra.postgresql.storages.resumes import ResumesDatabaseStorage
from tests.test_cases import StorageTestCase


class TestResumesDatabaseStorage(StorageTestCase):
    @pytest_asyncio.fixture(autouse=True)
    async def setup(self) -> None:
        self.storage = ResumesDatabaseStorage(session=self.db_session)

    async def test_create_and_get_resume_roundtrips_full_content_jsonb(self) -> None:
        content = self.factory.core.resume_full_content(summary="Builds reliable backend systems.")

        created = await self.storage.create_resume(
            params=ResumeCreateParams(
                title="Backend engineer",
                language=LanguageEnum.EN,
                content=content,
                author_username="admin",
            ),
        )
        loaded = await self.storage.get_resume(resume_id=created.id, author_username="admin")
        created_row = await self.db_session.get(ResumeModel, created.id)

        assert loaded.id == created.id
        assert loaded.title == "Backend engineer"
        assert loaded.language == LanguageEnum.EN
        assert loaded.author_username == "admin"
        assert loaded.content == content
        assert loaded.created_at.tzinfo == UTC
        assert loaded.updated_at.tzinfo == UTC
        assert created_row is not None
        assert created_row.language is LanguageEnum.EN
        assert created_row.content["experience"][0]["current_status"] == "current"
        assert created_row.content["experience"][0]["company"] == "Company"
        assert "is_current" not in created_row.content["experience"][0]
        assert "company_ru" not in created_row.content["experience"][0]

    async def test_list_resumes_orders_by_updated_at_then_id_and_paginates(self) -> None:
        await self.create_resume_row(
            resume_id=self.factory.core.hex_id(1),
            title="Older",
            author_username="admin",
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        await self.create_resume_row(
            resume_id=self.factory.core.hex_id(2),
            title="Tie lower id",
            author_username="admin",
            updated_at=datetime(2026, 1, 3, tzinfo=UTC),
        )
        await self.create_resume_row(
            resume_id=self.factory.core.hex_id(3),
            title="Tie higher id",
            author_username="admin",
            updated_at=datetime(2026, 1, 3, tzinfo=UTC),
        )
        await self.create_resume_row(
            resume_id=self.factory.core.hex_id(4),
            title="Other author",
            author_username="other-admin",
            updated_at=datetime(2026, 1, 3, tzinfo=UTC),
        )

        resumes, total_count = await self.storage.list_resumes(
            filters=ResumeFilters(
                page=1,
                page_size=2,
                search_query=None,
                author_username="admin",
            ),
        )

        assert self.collections.ids(resumes) == [
            self.factory.core.hex_id(3),
            self.factory.core.hex_id(2),
        ]
        assert total_count == 3

    async def test_update_resume_replaces_content(self) -> None:
        created = await self.storage.create_resume(
            params=ResumeCreateParams(
                title="Backend engineer",
                language=LanguageEnum.RU,
                content=self.factory.core.resume_full_content(summary="Старое описание."),
                author_username="admin",
            ),
        )
        replacement = self.factory.core.resume_empty_content(summary="Новое описание.")
        updated_at = created.updated_at + timedelta(minutes=5)

        updated = await self.storage.update_resume(
            resume=self.factory.core.resume(
                resume_id=created.id,
                title="Platform engineer",
                language=LanguageEnum.RU,
                content=replacement,
                author_username="admin",
                created_at=created.created_at.isoformat(),
                updated_at=updated_at.isoformat(),
            ),
        )

        assert updated.title == "Platform engineer"
        assert updated.language == LanguageEnum.RU
        assert updated.content == replacement
        assert updated.created_at == created.created_at
        assert updated.updated_at == updated_at

    async def test_get_resume_normalizes_nullable_content_jsonb(self) -> None:
        model = ResumeModel(
            id=self.factory.core.hex_id(50),
            title="Nullable resume",
            language=LanguageEnum.RU,
            author_username="admin",
            content=nullable_content_json(),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
        self.db_session.add(model)
        await self.db_session.flush()

        loaded = await self.storage.get_resume(
            resume_id=self.factory.core.hex_id(50), author_username="admin"
        )

        assert loaded.content.profile.full_name == ""
        assert loaded.content.profile.phone == ""
        assert loaded.content.summary.text == ""
        assert loaded.content.skills[0].category == ""
        assert loaded.content.skills[0].items == []
        assert loaded.content.experience[0].location == ""
        assert loaded.content.experience[0].current_status == ResumeCurrentStatusEnum.NOT_SET
        assert loaded.content.experience[0].end_date is None
        assert loaded.content.experience[0].highlights == []
        assert loaded.content.experience[0].projects[0].url == ""
        assert loaded.content.experience[0].projects[0].technologies == []

    async def test_delete_resume_removes_row(self) -> None:
        created = await self.storage.create_resume(
            params=ResumeCreateParams(
                title="Backend engineer",
                language=LanguageEnum.RU,
                content=self.factory.core.resume_full_content(summary="Удаляемое резюме."),
                author_username="admin",
            ),
        )

        await self.storage.delete_resume(resume_id=created.id, author_username="admin")

        with pytest.raises(ResumeNotFoundError):
            await self.storage.get_resume(resume_id=created.id, author_username="admin")

    async def test_other_author_resume_operations_raise_domain_error(self) -> None:
        await self.create_resume_row(
            resume_id=self.factory.core.hex_id(10),
            title="Other author",
            author_username="other-admin",
            updated_at=datetime(2026, 1, 3, tzinfo=UTC),
        )
        other_author_resume = self.factory.core.resume(
            resume_id=self.factory.core.hex_id(10),
            title="Attempted update",
            language=LanguageEnum.RU,
            content=self.factory.core.resume_empty_content(summary=""),
            author_username="admin",
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-02T00:00:00",
        )

        with pytest.raises(ResumeNotFoundError):
            await self.storage.get_resume(
                resume_id=self.factory.core.hex_id(10), author_username="admin"
            )
        with pytest.raises(ResumeNotFoundError):
            await self.storage.update_resume(resume=other_author_resume)
        with pytest.raises(ResumeNotFoundError):
            await self.storage.delete_resume(
                resume_id=self.factory.core.hex_id(10), author_username="admin"
            )

    async def test_missing_resume_operations_raise_domain_error(self) -> None:
        missing_resume = self.factory.core.resume(
            resume_id=self.factory.core.hex_id(404),
            title="Missing",
            language=LanguageEnum.RU,
            content=self.factory.core.resume_empty_content(summary=""),
            author_username="admin",
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-02T00:00:00",
        )

        with pytest.raises(ResumeNotFoundError):
            await self.storage.get_resume(
                resume_id=self.factory.core.hex_id(404), author_username="admin"
            )
        with pytest.raises(ResumeNotFoundError):
            await self.storage.update_resume(resume=missing_resume)
        with pytest.raises(ResumeNotFoundError):
            await self.storage.delete_resume(
                resume_id=self.factory.core.hex_id(404), author_username="admin"
            )

    async def create_resume_row(
        self,
        *,
        resume_id: str,
        title: str,
        author_username: str,
        updated_at: datetime,
    ) -> None:
        model = ResumeModel.from_domain_schema(
            resume=self.factory.core.resume(
                resume_id=resume_id,
                title=title,
                language=LanguageEnum.RU,
                content=self.factory.core.resume_full_content(summary=title),
                author_username=author_username,
                created_at="2026-01-01T00:00:00",
                updated_at=updated_at.isoformat(),
            ),
        )
        self.db_session.add(model)
        await self.db_session.flush()


def nullable_content_json() -> dict[str, object]:
    return {
        "profile": {
            "full_name": None,
            "role": None,
            "location": None,
            "email": None,
            "phone": None,
            "website_url": None,
            "linkedin_url": None,
            "github_url": None,
            "telegram": None,
        },
        "summary": {
            "text": None,
        },
        "skills": [
            {
                "category": None,
                "items": None,
            },
        ],
        "experience": [
            {
                "company": None,
                "position": None,
                "location": None,
                "start_date": None,
                "end_date": None,
                "current_status": None,
                "summary": None,
                "highlights": None,
                "technologies": [],
                "projects": [
                    {
                        "name": None,
                        "role": None,
                        "description": None,
                        "highlights": [],
                        "technologies": None,
                        "url": None,
                    },
                ],
            },
        ],
        "education": [],
        "languages": [],
        "certifications": [],
        "additional_sections": [],
    }
