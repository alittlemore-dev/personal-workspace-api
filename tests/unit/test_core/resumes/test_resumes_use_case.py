from datetime import UTC, datetime
from typing import Any
from unittest.mock import Mock

import pytest

from core.i18n.enums import LanguageEnum
from core.resumes.enums import ResumeExportFormatEnum
from core.resumes.exceptions import ResumeNotFoundError
from core.resumes.exporters import ResumeDocumentExporter
from core.resumes.schemas import (
    ResumeCreateParams,
    ResumeExport,
    ResumeExportParams,
    ResumeFilters,
    Resumes,
    ResumeUpdateParams,
)
from core.resumes.storages import ResumesStorage
from core.resumes.use_cases import ResumesUseCase
from tests.test_cases import TestCase

CURRENT_DATETIME = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


class TestResumesUseCase(TestCase):
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.storage = Mock(spec=ResumesStorage)
        self.exporter = Mock(spec=ResumeDocumentExporter)
        self.use_case = ResumesUseCase(storage=self.storage, exporter=self.exporter)

    def test_resume_filters_require_explicit_values(self) -> None:
        missing_filter_values: dict[str, Any] = {}

        with pytest.raises(TypeError, match="required keyword-only arguments"):
            ResumeFilters(**missing_filter_values)

    async def test_list_resumes_builds_page_from_storage_rows(self) -> None:
        filters = ResumeFilters(
            page=2,
            page_size=10,
            search_query="backend",
            author_username="test",
        )
        resume = self.factory.core.resume(
            resume_id=self.factory.core.hex_id(1),
            content=self.factory.core.resume_full_content(
                summary="Builds reliable systems.",
                skill_items=["Python"],
            ),
        )
        self.storage.list_resumes.return_value = ([resume], 21)

        result = await self.use_case.list_resumes(filters=filters)

        assert result == Resumes(values=[resume], total_count=21, total_pages=3)
        assert filters.limit == 10
        assert filters.offset == 10
        self.storage.list_resumes.assert_called_once_with(filters=filters)

    async def test_list_resumes_requires_pagination_before_storage_call(self) -> None:
        with pytest.raises(ValueError, match="pagination required"):
            await self.use_case.list_resumes(
                filters=ResumeFilters(
                    page=None,
                    page_size=None,
                    search_query=None,
                    author_username="test",
                ),
            )

        self.storage.list_resumes.assert_not_called()

    async def test_get_resume_delegates_to_storage(self) -> None:
        expected = self.factory.core.resume(
            resume_id=self.factory.core.hex_id(1),
            content=self.factory.core.resume_full_content(
                summary="Builds reliable systems.",
                skill_items=["Python"],
            ),
        )
        self.storage.get_resume.return_value = expected

        result = await self.use_case.get_resume(
            resume_id=self.factory.core.hex_id(1), author_username="test"
        )

        assert result == expected
        self.storage.get_resume.assert_called_once_with(
            resume_id=self.factory.core.hex_id(1),
            author_username="test",
        )

    async def test_get_resume_propagates_not_found(self) -> None:
        self.storage.get_resume.side_effect = ResumeNotFoundError

        with pytest.raises(ResumeNotFoundError):
            await self.use_case.get_resume(
                resume_id=self.factory.core.hex_id(404), author_username="test"
            )

    async def test_create_resume_persists_explicit_content(self) -> None:
        content = self.factory.core.resume_full_content(
            summary="Builds reliable systems.",
            skill_items=["Python"],
        )
        params = ResumeCreateParams(
            title="Backend engineer",
            language=LanguageEnum.EN,
            content=content,
            author_username="test",
        )
        expected = self.factory.core.resume(resume_id=self.factory.core.hex_id(1), content=content)
        self.storage.create_resume.return_value = expected

        result = await self.use_case.create_resume(params=params)

        assert result == expected
        self.storage.create_resume.assert_called_once_with(params=params)

    async def test_update_resume_replaces_whole_content(self) -> None:
        existing_content = self.factory.core.resume_full_content(
            summary="Old summary.",
            skill_items=["Python", "SQL"],
        )
        existing_resume = self.factory.core.resume(
            resume_id=self.factory.core.hex_id(1),
            content=existing_content,
            author_username="original-author",
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-02T00:00:00",
        )
        replacement_content = self.factory.core.resume_empty_content(summary="Updated summary.")
        params = ResumeUpdateParams(
            title="Platform engineer",
            language=LanguageEnum.RU,
            content=replacement_content,
        )
        expected = self.factory.core.resume(
            resume_id=self.factory.core.hex_id(1),
            content=replacement_content,
            author_username="original-author",
        )
        self.storage.get_resume.return_value = existing_resume
        self.storage.update_resume.return_value = expected

        result = await self.use_case.update_resume(
            resume_id=self.factory.core.hex_id(1),
            params=params,
            author_username="original-author",
            current_datetime=CURRENT_DATETIME,
        )

        assert result == expected
        self.storage.get_resume.assert_called_once_with(
            resume_id=self.factory.core.hex_id(1),
            author_username="original-author",
        )
        self.storage.update_resume.assert_called_once()
        updated_resume = self.storage.update_resume.call_args.kwargs["resume"]
        assert updated_resume.id == existing_resume.id
        assert updated_resume.author_username == "original-author"
        assert updated_resume.created_at == existing_resume.created_at
        assert updated_resume.updated_at == CURRENT_DATETIME
        assert updated_resume.title == "Platform engineer"
        assert updated_resume.language == LanguageEnum.RU
        assert updated_resume.content == replacement_content
        assert updated_resume.content.experience == []

    async def test_delete_resume_delegates_to_storage(self) -> None:
        await self.use_case.delete_resume(
            resume_id=self.factory.core.hex_id(1), author_username="test"
        )

        self.storage.delete_resume.assert_called_once_with(
            resume_id=self.factory.core.hex_id(1),
            author_username="test",
        )

    async def test_export_resume_checks_owner_and_exports_current_payload(self) -> None:
        existing_resume = self.factory.core.resume(
            resume_id=self.factory.core.hex_id(1),
            content=self.factory.core.resume_full_content(
                summary="Saved summary",
                skill_items=["Python"],
            ),
        )
        export_content = self.factory.core.resume_full_content(
            summary="Unsaved summary",
            skill_items=["Litestar"],
        )
        params = ResumeExportParams(
            format=ResumeExportFormatEnum.PDF,
            title="Unsaved resume",
            language=LanguageEnum.EN,
            content=export_content,
        )
        expected = ResumeExport(format=ResumeExportFormatEnum.PDF, content=b"%PDF-1.4")
        self.storage.get_resume.return_value = existing_resume
        self.exporter.export_resume.return_value = expected

        result = await self.use_case.export_resume(
            resume_id=self.factory.core.hex_id(1),
            params=params,
            author_username="test",
        )

        assert result == expected
        self.storage.get_resume.assert_called_once_with(
            resume_id=self.factory.core.hex_id(1),
            author_username="test",
        )
        self.exporter.export_resume.assert_called_once_with(params=params)

    async def test_export_resume_propagates_not_found_before_rendering(self) -> None:
        params = ResumeExportParams(
            format=ResumeExportFormatEnum.DOCX,
            title="Resume",
            language=LanguageEnum.RU,
            content=self.factory.core.resume_full_content(
                summary="Summary",
                skill_items=["Python"],
            ),
        )
        self.storage.get_resume.side_effect = ResumeNotFoundError

        with pytest.raises(ResumeNotFoundError):
            await self.use_case.export_resume(
                resume_id=self.factory.core.hex_id(404),
                params=params,
                author_username="test",
            )

        self.exporter.export_resume.assert_not_called()
