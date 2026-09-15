from datetime import date, datetime

import pytest
import pytest_asyncio
from httpx import codes

from core.i18n.enums import LanguageEnum
from core.resumes.enums import ResumeCurrentStatusEnum, ResumeExportFormatEnum
from core.resumes.exceptions import ResumeNotFoundError
from core.resumes.schemas import (
    ResumeCreateParams,
    ResumeExperienceItem,
    ResumeExport,
    ResumeExportParams,
    ResumeFilters,
    ResumeProjectItem,
    ResumeUpdateParams,
)
from tests.test_cases import ApiTestCase
from tests.unit.conftest import TEST_OWNER_USERNAME


def experience_payload() -> dict[str, object]:
    return {
        "company": "Company",
        "position": "Engineer",
        "location": "",
        "startDate": "2024-01-01",
        "endDate": None,
        "currentStatus": "current",
        "summary": "Built a platform.",
        "highlights": ["Reduced latency"],
        "technologies": ["Python"],
        "projects": [
            {
                "name": "Portfolio",
                "role": "Creator",
                "description": "Site and knowledge base",
                "highlights": ["Hybrid CSR"],
                "technologies": ["Litestar", "Angular"],
                "url": "https://example.com",
            },
        ],
    }


class TestResumesApi(ApiTestCase):
    @pytest_asyncio.fixture(autouse=True)
    async def setup(self) -> None:
        self.use_case = await self.container.get_resumes_use_case()

    def test_list_maps_pagination_and_current_author(self) -> None:
        resume = self.factory.core.resume(resume_id=1, title="Backend resume")
        self.use_case.list_resumes.return_value = self.factory.core.resumes(
            values=[resume],
            total_count=1,
            total_pages=1,
        )

        response = self.api.get_resumes(page=2, page_size=10)

        self.asserts.status(response=response, expected_status=codes.OK)
        assert response.json()["resumes"][0]["id"] == self.factory.core.hex_id(1)
        self.use_case.list_resumes.assert_awaited_once_with(
            filters=ResumeFilters(
                page=2,
                page_size=10,
                search_query=None,
                author_username=TEST_OWNER_USERNAME,
            ),
        )

    def test_create_maps_complete_current_payload(self) -> None:
        experience = [
            ResumeExperienceItem(
                company="Company",
                position="Engineer",
                location="",
                start_date=date(2024, 1, 1),
                end_date=None,
                current_status=ResumeCurrentStatusEnum.CURRENT,
                summary="Built a platform.",
                highlights=["Reduced latency"],
                technologies=["Python"],
                projects=[
                    ResumeProjectItem(
                        name="Portfolio",
                        role="Creator",
                        description="Site and knowledge base",
                        highlights=["Hybrid CSR"],
                        technologies=["Litestar", "Angular"],
                        url="https://example.com",
                    ),
                ],
            ),
        ]
        content = self.factory.core.resume_content(
            full_name="Dmitriy",
            role="Backend engineer",
            summary="Current summary",
            experience=experience,
        )
        self.use_case.create_resume.return_value = self.factory.core.resume(
            resume_id=2,
            title="Target resume",
            language=LanguageEnum.EN,
            content=content,
        )

        response = self.api.post_create_resume(
            data=self.factory.api.resume_request(
                title="Target resume",
                language="en",
                content=self.factory.api.resume_content(
                    full_name="Dmitriy",
                    role="Backend engineer",
                    summary="Current summary",
                    experience=[experience_payload()],
                ),
            ),
        )

        self.asserts.status(response=response, expected_status=codes.CREATED)
        assert response.json()["content"]["experience"][0]["projects"][0]["name"] == ("Portfolio")
        self.use_case.create_resume.assert_awaited_once_with(
            params=ResumeCreateParams(
                title="Target resume",
                language=LanguageEnum.EN,
                content=content,
                author_username=TEST_OWNER_USERNAME,
            ),
        )

    def test_create_rejects_missing_language(self) -> None:
        payload = self.factory.api.resume_request()
        del payload["language"]

        response = self.api.post_create_resume(data=payload)

        self.asserts.status(response=response, expected_status=codes.BAD_REQUEST)
        self.use_case.create_resume.assert_not_awaited()

    @pytest.mark.parametrize(
        ("title", "language"),
        [("Backend resume", "de"), ("   ", "ru")],
    )
    def test_create_rejects_unknown_language_or_blank_title(
        self,
        title: str,
        language: str,
    ) -> None:
        response = self.api.post_create_resume(
            data=self.factory.api.resume_request(title=title, language=language),
        )

        self.asserts.status(response=response, expected_status=codes.BAD_REQUEST)
        self.use_case.create_resume.assert_not_awaited()

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("fullName", "   "),
            ("role", "   "),
            ("email", "not-an-email"),
            ("websiteUrl", "mailto:me@example.com"),
        ],
    )
    def test_create_rejects_invalid_profile_fields(self, field: str, value: str) -> None:
        content = self.factory.api.resume_content()
        content["profile"][field] = value

        response = self.api.post_create_resume(
            data=self.factory.api.resume_request(content=content),
        )

        self.asserts.status(response=response, expected_status=codes.BAD_REQUEST)
        self.use_case.create_resume.assert_not_awaited()

    @pytest.mark.parametrize(
        ("field", "value"),
        [("category", "   "), ("items", ["Python", "   "])],
    )
    def test_create_rejects_invalid_skill_fields(
        self,
        field: str,
        value: str | list[str],
    ) -> None:
        content = self.factory.api.resume_content()
        content["skills"][0][field] = value

        response = self.api.post_create_resume(
            data=self.factory.api.resume_request(content=content),
        )

        self.asserts.status(response=response, expected_status=codes.BAD_REQUEST)
        self.use_case.create_resume.assert_not_awaited()

    def test_create_allows_empty_repeatable_sections(self) -> None:
        content = self.factory.api.resume_content()
        for field in (
            "skills",
            "experience",
            "education",
            "languages",
            "certifications",
            "additionalSections",
        ):
            content[field] = []
        domain_content = self.factory.core.resume_content(skills=[], experience=[])
        self.use_case.create_resume.return_value = self.factory.core.resume(
            resume_id=2,
            content=domain_content,
        )

        response = self.api.post_create_resume(
            data=self.factory.api.resume_request(content=content),
        )

        self.asserts.status(response=response, expected_status=codes.CREATED)
        assert self.use_case.create_resume.await_args.kwargs["params"].content == domain_content

    def test_create_rejects_invalid_nested_experience_and_long_summary(self) -> None:
        invalid_experience = experience_payload()
        invalid_experience["company"] = "   "
        content = self.factory.api.resume_content(experience=[invalid_experience])

        invalid_experience_response = self.api.post_create_resume(
            data=self.factory.api.resume_request(content=content),
        )
        long_summary_response = self.api.post_create_resume(
            data=self.factory.api.resume_request(
                content=self.factory.api.resume_content(summary="x" * 10_001),
            ),
        )

        self.asserts.status(
            response=invalid_experience_response,
            expected_status=codes.BAD_REQUEST,
        )
        self.asserts.status(
            response=long_summary_response,
            expected_status=codes.BAD_REQUEST,
        )
        self.use_case.create_resume.assert_not_awaited()

    def test_update_maps_id_author_and_request_datetime(self) -> None:
        content = self.factory.core.resume_content(summary="Updated")
        self.use_case.update_resume.return_value = self.factory.core.resume(
            resume_id=3,
            title="Updated resume",
            language=LanguageEnum.EN,
            content=content,
        )

        response = self.api.put_update_resume(
            resume_id=3,
            data=self.factory.api.resume_request(
                title="Updated resume",
                language="en",
                content=self.factory.api.resume_content(summary="Updated"),
            ),
        )

        self.asserts.status(response=response, expected_status=codes.OK)
        call = self.use_case.update_resume.await_args.kwargs
        assert call["resume_id"] == self.factory.core.hex_id(3)
        assert call["params"] == ResumeUpdateParams(
            title="Updated resume",
            language=LanguageEnum.EN,
            content=content,
        )
        assert call["author_username"] == TEST_OWNER_USERNAME
        assert isinstance(call["current_datetime"], datetime)

    def test_get_missing_resume_uses_stable_not_found_contract(self) -> None:
        self.use_case.get_resume.side_effect = ResumeNotFoundError()

        response = self.api.get_resume(resume_id=404)

        self.asserts.error_message(
            response=response,
            expected_status=codes.NOT_FOUND,
            expected_message=ResumeNotFoundError.message,
        )
        self.use_case.get_resume.assert_awaited_once_with(
            resume_id=self.factory.core.hex_id(404),
            author_username=TEST_OWNER_USERNAME,
        )

    def test_export_uses_unsaved_current_payload(self) -> None:
        content = self.factory.core.resume_content(summary="Unsaved current summary")
        self.use_case.export_resume.return_value = ResumeExport(
            format=ResumeExportFormatEnum.PDF,
            content=b"%PDF-1.4",
        )

        response = self.api.post_export_resume(
            resume_id=3,
            data={
                "format": "pdf",
                **self.factory.api.resume_request(
                    title="Target resume",
                    language="en",
                    content=self.factory.api.resume_content(
                        summary="Unsaved current summary",
                    ),
                ),
            },
        )

        self.asserts.status(response=response, expected_status=codes.OK)
        assert response.content == b"%PDF-1.4"
        assert response.headers["content-type"] == "application/pdf"
        self.use_case.export_resume.assert_awaited_once_with(
            resume_id=self.factory.core.hex_id(3),
            params=ResumeExportParams(
                format=ResumeExportFormatEnum.PDF,
                title="Target resume",
                language=LanguageEnum.EN,
                content=content,
            ),
            author_username=TEST_OWNER_USERNAME,
        )

    def test_export_supports_docx_and_rejects_unknown_format(self) -> None:
        self.use_case.export_resume.return_value = ResumeExport(
            format=ResumeExportFormatEnum.DOCX,
            content=b"docx-bytes",
        )

        docx_response = self.api.post_export_resume(
            resume_id=5,
            data={"format": "docx", **self.factory.api.resume_request()},
        )

        self.asserts.status(response=docx_response, expected_status=codes.OK)
        assert docx_response.content == b"docx-bytes"
        assert docx_response.headers["content-type"] == (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

        self.use_case.export_resume.reset_mock()
        invalid_response = self.api.post_export_resume(
            resume_id=5,
            data={"format": "xlsx", **self.factory.api.resume_request()},
        )

        self.asserts.status(response=invalid_response, expected_status=codes.BAD_REQUEST)
        self.use_case.export_resume.assert_not_awaited()

    @pytest.mark.parametrize("operation", ["export", "delete"])
    def test_missing_resume_mutations_use_stable_not_found_contract(
        self,
        operation: str,
    ) -> None:
        if operation == "export":
            self.use_case.export_resume.side_effect = ResumeNotFoundError()
            response = self.api.post_export_resume(
                resume_id=404,
                data={"format": "pdf", **self.factory.api.resume_request()},
            )
        else:
            self.use_case.delete_resume.side_effect = ResumeNotFoundError()
            response = self.api.delete_resume(resume_id=404)

        self.asserts.error_message(
            response=response,
            expected_status=codes.NOT_FOUND,
            expected_message=ResumeNotFoundError.message,
        )

    def test_delete_maps_current_author(self) -> None:
        response = self.api.delete_resume(resume_id=3)

        self.asserts.status(response=response, expected_status=codes.NO_CONTENT)
        self.use_case.delete_resume.assert_awaited_once_with(
            resume_id=self.factory.core.hex_id(3),
            author_username=TEST_OWNER_USERNAME,
        )
