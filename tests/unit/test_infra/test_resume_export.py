import io
import re
from datetime import date
from zipfile import ZipFile

from pypdf import PdfReader

from core.i18n.enums import LanguageEnum
from core.resumes.enums import ResumeCurrentStatusEnum, ResumeExportFormatEnum
from core.resumes.schemas import ResumeExperienceItem, ResumeExportParams
from infra.config.constants import constants
from infra.resume_export.document_exporter import ResumeDocumentExporterImpl
from tests.test_cases import TestCase


class TestResumeExportConstants:
    def test_vendored_font_paths_exist(self) -> None:
        assert constants.resume_export.font_regular_path.is_file()
        assert constants.resume_export.font_bold_path.is_file()
        assert constants.resume_export.font_license_path.is_file()


class TestResumeDocumentExporter(TestCase):
    def test_pdf_export_preserves_authored_xml_sensitive_text(self) -> None:
        exporter = self._exporter()
        summary = 'Owner & <operator> said "don\'t" > "ship".'

        document = exporter.export_resume(
            params=ResumeExportParams(
                format=ResumeExportFormatEnum.PDF,
                title="Backend resume",
                language=LanguageEnum.EN,
                content=self.factory.core.resume_content(summary=summary),
            ),
        )

        assert summary in self._extract_pdf_text(content=document.content)

    def test_pdf_export_is_linear_and_ats_readable(self) -> None:
        exporter = self._exporter()

        document = exporter.export_resume(
            params=ResumeExportParams(
                format=ResumeExportFormatEnum.PDF,
                title="Backend resume",
                language=LanguageEnum.EN,
                content=self.factory.core.resume_full_content(
                    summary="Backend engineer building reliable Python systems.",
                    skill_items=["Python", "PostgreSQL", "Docker"],
                ),
            ),
        )

        text = self._extract_pdf_text(content=document.content)
        self._assert_text_order(
            text=text,
            expected_parts=[
                "Dmitriy Ivanov",
                "Backend engineer",
                "Moscow | dmitriy@example.com | +79990000000",
                "Professional Summary",
                "Backend engineer building reliable Python systems.",
                "Skills",
                "Languages: Python, PostgreSQL, Docker",
                "Work Experience",
                "Engineer | Company",
                "Moscow | Jan 2023 - Present",
                "- Reduced response time",
                "Technologies: Python, PostgreSQL",
                "Project: Portfolio | Creator",
                "- Angular CSR",
                "Education",
                "University | Bachelor | Computer science",
                "Moscow | Sep 2014 - Jun 2018",
                "Certifications",
                "Certificate | Provider",
                "Languages",
                "English | C1",
                "Publications",
            ],
        )
        assert not re.search(r"(?m)^\s*•\s*$", text)

    def test_pdf_export_preserves_cyrillic_text_for_ru_resume(self) -> None:
        exporter = self._exporter()

        document = exporter.export_resume(
            params=ResumeExportParams(
                format=ResumeExportFormatEnum.PDF,
                title="Backend resume",
                language=LanguageEnum.RU,
                content=self.factory.core.resume_content(
                    full_name="Дмитрий Иванов",
                    role="Backend инженер",
                    summary="Строит надежные backend-системы.",
                    experience=[
                        ResumeExperienceItem(
                            company="Компания",
                            position="Инженер",
                            location="Москва",
                            start_date=date(2023, 1, 1),
                            end_date=None,
                            current_status=ResumeCurrentStatusEnum.CURRENT,
                            summary="Развивает платформенные сервисы.",
                            highlights=["Упростил экспорт резюме"],
                            technologies=["Python"],
                            projects=[],
                        ),
                    ],
                ),
            ),
        )

        text = self._extract_pdf_text(content=document.content)
        self._assert_text_order(
            text=text,
            expected_parts=[
                "Дмитрий Иванов",
                "Backend инженер",
                "Профессиональный профиль",
                "Строит надежные backend-системы.",
                "Опыт работы",
                "Инженер | Компания",
                "Москва | 01.2023 - настоящее время",
                "- Упростил экспорт резюме",
            ],
        )

    def test_docx_export_uses_plain_linear_structure(self) -> None:
        exporter = self._exporter()

        document = exporter.export_resume(
            params=ResumeExportParams(
                format=ResumeExportFormatEnum.DOCX,
                title="Backend resume",
                language=LanguageEnum.EN,
                content=self.factory.core.resume_full_content(
                    summary="Backend engineer building reliable Python systems.",
                    skill_items=["Python", "PostgreSQL", "Docker"],
                ),
            ),
        )

        with ZipFile(io.BytesIO(document.content)) as archive:
            names = archive.namelist()
            document_xml = archive.read("word/document.xml").decode()
            styles_xml = archive.read("word/styles.xml").decode()

        self._assert_text_order(
            text=self._extract_word_text(document_xml=document_xml),
            expected_parts=[
                "Dmitriy Ivanov",
                "Backend engineer",
                "Moscow | dmitriy@example.com | +79990000000",
                "Professional Summary",
                "Skills",
                "Work Experience",
                "Engineer | Company",
                "Moscow | Jan 2023 - Present",
                "- Reduced response time",
                "Project: Portfolio | Creator",
                "Education",
                "Certifications",
                "Languages",
            ],
        )
        assert "<w:tbl" not in document_xml
        assert "<w:drawing" not in document_xml
        assert all(not name.startswith("word/header") for name in names)
        assert all(not name.startswith("word/footer") for name in names)
        assert 'w:val="Title"' not in document_xml
        assert 'w:val="Heading1"' not in document_xml
        assert 'w:val="Heading2"' not in document_xml
        assert 'w:val="ListBullet"' not in document_xml
        assert 'w:styleId="ResumeName"' in styles_xml
        assert 'w:styleId="ResumeSection"' in styles_xml
        assert 'w:ascii="Arial"' in styles_xml

    def test_pdf_export_generates_pdf_bytes(self) -> None:
        exporter = self._exporter()

        document = exporter.export_resume(
            params=ResumeExportParams(
                format=ResumeExportFormatEnum.PDF,
                title="Backend resume",
                language=LanguageEnum.RU,
                content=self.factory.core.resume_content(
                    full_name="Дмитрий Иванов",
                    role="Backend инженер",
                    summary="Строит надежные backend-системы.",
                ),
            ),
        )

        assert document.format == ResumeExportFormatEnum.PDF
        assert document.content.startswith(b"%PDF")

    def test_docx_export_generates_docx_with_resume_text(self) -> None:
        exporter = self._exporter()

        document = exporter.export_resume(
            params=ResumeExportParams(
                format=ResumeExportFormatEnum.DOCX,
                title="Backend resume",
                language=LanguageEnum.EN,
                content=self.factory.core.resume_content(
                    full_name="Candidate Name",
                    role="Backend engineer",
                    summary="Builds reliable backend systems.",
                ),
            ),
        )

        assert document.format == ResumeExportFormatEnum.DOCX
        with ZipFile(io.BytesIO(document.content)) as archive:
            document_xml = archive.read("word/document.xml").decode()
        assert "Candidate Name" in document_xml
        assert "Builds reliable backend systems." in document_xml

    def _exporter(self) -> ResumeDocumentExporterImpl:
        return ResumeDocumentExporterImpl(
            font_regular_path=constants.resume_export.font_regular_path,
            font_bold_path=constants.resume_export.font_bold_path,
            font_regular_name=constants.resume_export.font_regular_name,
            font_bold_name=constants.resume_export.font_bold_name,
        )

    def _extract_pdf_text(self, *, content: bytes) -> str:
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text(extraction_mode="layout") or "" for page in reader.pages)

    def _extract_word_text(self, *, document_xml: str) -> str:
        return "\n".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", document_xml))

    def _assert_text_order(self, *, text: str, expected_parts: list[str]) -> None:
        cursor = 0
        for part in expected_parts:
            index = text.find(part, cursor)
            assert index >= 0, f"Expected {part!r} after offset {cursor} in:\n{text}"
            cursor = index + len(part)
