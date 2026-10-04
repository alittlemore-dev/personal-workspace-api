from copy import deepcopy
from io import BytesIO
from typing import Any

import pytest
from pydantic import ValidationError
from pypdf import PdfWriter

from core.resumes.enums import ResumeDateFormatEnum, ResumeExportFormatEnum, ResumeSectionEnum
from core.resumes.schemas import ResumeExport
from entrypoints.litestar.api.resumes.responses import ResumeExportResponse
from entrypoints.litestar.api.resumes.schemas import ResumeExportRequestSchema, ResumeRequestSchema
from tests.helpers.factories.api import ApiFactoryHelper
from tests.unit.test_api.resumes.test_resumes import experience_payload


def request_content() -> dict[str, Any]:
    return ApiFactoryHelper.resume_content(experience=[experience_payload()])


def test_resume_accepts_project_scale_and_company_website() -> None:
    content = request_content()
    content["experience"][0]["companyWebsiteUrl"] = "https://company.example"
    content["experience"][0]["projects"][0].update(
        teamSize="5–7 engineers",
        scale="2M requests/day",
    )
    resume = ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))

    assert resume.content.experience[0].company_website_url == "https://company.example"
    assert resume.content.experience[0].projects[0].team_size == "5–7 engineers"
    assert resume.content.experience[0].projects[0].scale == "2M requests/day"


def test_resume_photo_requires_file_reference() -> None:
    content = request_content()
    content["profile"]["photoFileId"] = "0" * 32
    ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))

    content["profile"]["photoFileId"] = "data:image/jpeg;base64,ZmFrZQ=="
    with pytest.raises(ValidationError):
        ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))


@pytest.mark.parametrize(
    ("section", "count"),
    [
        ("experience", 21),
        ("languages", 10),
        ("certifications", 16),
        ("additionalSections", 7),
        ("skills", 13),
    ],
)
def test_rejects_excessive_top_level_sections(section: str, count: int) -> None:
    content = request_content()
    if section == "experience":
        item = experience_payload()
    elif section == "languages":
        item = {"name": "English", "proficiency": "Native"}
    elif section == "certifications":
        item = {
            "name": "Certificate",
            "issuer": "Issuer",
            "issuedOn": None,
            "expiresOn": None,
            "credentialUrl": "",
        }
    elif section == "additionalSections":
        item = {"title": "Awards", "items": [{"title": "Award", "description": "", "url": ""}]}
    else:
        item = {"category": "Backend", "items": ["Python"]}
    content[section] = [deepcopy(item) for _ in range(count)]
    with pytest.raises(ValidationError):
        ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))


def test_allows_sixteen_experience_entries() -> None:
    content = request_content()
    content["experience"] = [experience_payload() for _ in range(16)]
    ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))


def test_rejects_sixteenth_project_within_one_job() -> None:
    content = request_content()
    project = experience_payload()["projects"][0]
    content["experience"][0]["projects"] = [deepcopy(project) for _ in range(16)]
    with pytest.raises(ValidationError):
        ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))


def test_project_technologies_allow_fifty_but_reject_fifty_one() -> None:
    content = request_content()
    technologies = [f"Technology {index}" for index in range(50)]
    content["experience"][0]["projects"][0]["technologies"] = technologies
    ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))

    content["experience"][0]["projects"][0]["technologies"] = [
        *technologies,
        "Technology 50",
    ]
    with pytest.raises(ValidationError):
        ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))


@pytest.mark.parametrize(
    "change",
    [
        {"endDate": "2023-12-31"},
        {"currentStatus": "current", "endDate": "2025-01-01"},
        {"summary": "", "highlights": [], "projects": []},
        {"technologies": ["Python", " python "]},
    ],
)
def test_rejects_inconsistent_experience(change: dict[str, object]) -> None:
    content = request_content()
    content["experience"][0].update(change)
    with pytest.raises(ValidationError):
        ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))


def test_rejects_empty_skill_group_and_oversized_highlight() -> None:
    content = request_content()
    content["skills"][0]["items"] = []
    with pytest.raises(ValidationError):
        ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))
    content["skills"][0]["items"] = ["Python"]
    content["experience"][0]["highlights"] = ["x" * 513]
    with pytest.raises(ValidationError):
        ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))


def test_rejects_duplicate_languages_and_reversed_certification_dates() -> None:
    content = request_content()
    content["languages"] = [
        {"name": "English", "proficiency": "Advanced"},
        {"name": " english ", "proficiency": "Native"},
    ]
    with pytest.raises(ValidationError):
        ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))

    content["languages"] = []
    content["certifications"] = [
        {
            "name": "Certificate",
            "issuer": "Issuer",
            "issuedOn": "2025-01-01",
            "expiresOn": "2024-12-31",
            "credentialUrl": "",
        },
    ]
    with pytest.raises(ValidationError):
        ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))


def test_ongoing_education_can_omit_end_date_but_cannot_end_before_start() -> None:
    content = request_content()
    education = {
        "institution": "University",
        "degree": "Bachelor",
        "field": "Computer science",
        "location": "Yerevan",
        "startDate": "2024-09-01",
        "endDate": None,
        "description": "",
    }
    content["education"] = [education]
    ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))

    education["endDate"] = "2024-08-31"
    with pytest.raises(ValidationError):
        ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))


def test_rejects_total_skill_and_project_limits() -> None:
    content = request_content()
    content["skills"] = [
        {"category": f"Group {group}", "items": [f"Skill {item}" for item in range(30)]}
        for group in range(7)
    ]
    with pytest.raises(ValidationError):
        ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))

    content["skills"] = []
    item = experience_payload()
    item["projects"] = [deepcopy(item["projects"][0]) for _ in range(15)]
    content["experience"] = [deepcopy(item) for _ in range(7)]
    with pytest.raises(ValidationError):
        ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))


def test_rejects_excessive_total_text_within_individual_item_limits() -> None:
    content = request_content()
    content["skills"] = []
    item = experience_payload()
    project = item["projects"][0]
    project["description"] = "x" * 600
    item["projects"] = [deepcopy(project) for _ in range(14)]
    content["experience"] = [deepcopy(item) for _ in range(7)]

    with pytest.raises(ValidationError, match="resume text exceeds limit"):
        ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))


def test_pdf_export_reports_actual_page_count() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.add_blank_page(width=595, height=842)
    output = BytesIO()
    writer.write(output)

    response = ResumeExportResponse.from_resume_export(
        resume_id="resume-id",
        document=ResumeExport(format=ResumeExportFormatEnum.PDF, content=output.getvalue()),
    )

    assert response.headers["X-Resume-Page-Count"] == "2"


@pytest.mark.parametrize("date_format", list(ResumeDateFormatEnum))
def test_resume_requires_explicit_date_settings(date_format: ResumeDateFormatEnum) -> None:
    content = request_content()
    content["settings"] = {
        "dateFormat": date_format.value,
        "sectionOrder": [],
        "hiddenSections": [],
    }
    request = ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))
    assert (
        request.to_create_schema(author_username="owner").content.settings.date_format
        is date_format
    )
    assert request.model_dump(by_alias=True)["content"]["settings"] == {
        "dateFormat": date_format.value,
        "sectionOrder": [],
        "hiddenSections": [],
    }
    content.pop("settings")
    with pytest.raises(ValidationError):
        ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))


@pytest.mark.parametrize("settings", [None, {}, {"dateFormat": "unknown"}, {"dateFormat": None}])
def test_resume_rejects_missing_or_invalid_date_format(settings: object) -> None:
    content = request_content()
    content["settings"] = settings
    with pytest.raises(ValidationError):
        ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sectionOrder", ["summary"]),
        ("sectionOrder", ["summary"] * 7),
        ("sectionOrder", [section.value for section in ResumeSectionEnum] + ["summary"]),
        ("sectionOrder", ["unknown"]),
        ("sectionOrder", None),
        ("hiddenSections", ["summary", "summary"]),
        ("hiddenSections", ["profile"]),
        ("hiddenSections", None),
    ],
)
def test_resume_rejects_invalid_section_settings(field: str, value: object) -> None:
    content = request_content()
    content["settings"][field] = value
    with pytest.raises(ValidationError):
        ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))


@pytest.mark.parametrize("field", ["sectionOrder", "hiddenSections"])
def test_resume_requires_explicit_section_settings(field: str) -> None:
    content = request_content()
    content["settings"].pop(field)
    with pytest.raises(ValidationError):
        ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))


def test_section_settings_are_preserved_in_create_update_and_export() -> None:
    order = list(reversed(ResumeSectionEnum))
    hidden = [ResumeSectionEnum.EDUCATION, ResumeSectionEnum.LANGUAGES]
    content = ApiFactoryHelper.resume_content(
        section_order=[section.value for section in order],
        hidden_sections=[section.value for section in hidden],
    )
    request = ResumeExportRequestSchema.model_validate(
        {
            **ApiFactoryHelper.resume_request(content=content),
            "format": "pdf",
            "theme": "accent",
        },
    )
    for settings in (
        request.to_create_schema(author_username="owner").content.settings,
        request.to_update_schema().content.settings,
        request.to_export_schema().content.settings,
    ):
        assert settings.section_order == order
        assert settings.hidden_sections == hidden
    assert request.model_dump(by_alias=True)["content"]["settings"] == content["settings"]


def test_hidden_sections_keep_authored_content_validation() -> None:
    content = request_content()
    content["settings"]["hiddenSections"] = ["experience"]
    content["experience"][0]["projects"][0]["description"] = ""
    content["experience"][0]["projects"][0]["highlights"] = []
    with pytest.raises(ValidationError, match="project requires"):
        ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))


def test_project_role_accepts_blank_but_requires_field_and_experience_position() -> None:
    content = request_content()
    project = content["experience"][0]["projects"][0]
    project["role"] = "   "
    resume = ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))
    assert resume.content.experience[0].projects[0].role == ""
    project.pop("role")
    with pytest.raises(ValidationError):
        ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))
    project["role"] = ""
    content["experience"][0]["position"] = " "
    with pytest.raises(ValidationError):
        ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))


@pytest.mark.parametrize("section", ["experience", "education", "certifications"])
@pytest.mark.parametrize(
    ("start", "end", "valid"),
    [
        (None, None, True),
        ("2024-08-09", None, True),
        (None, "2024-08-09", False),
        ("2024-08-09", "2024-08-09", True),
        ("2024-08-09", "2024-08-08", False),
    ],
)
def test_resume_date_periods(section: str, start: str | None, end: str | None, valid: bool) -> None:
    content = request_content()
    if section == "experience":
        item = experience_payload()
        item.update(startDate=start, endDate=end, currentStatus="notCurrent")
    elif section == "education":
        item = {
            "institution": "University",
            "degree": "Bachelor",
            "field": "Engineering",
            "location": "Yerevan",
            "description": "",
            "startDate": start,
            "endDate": end,
        }
    else:
        item = {
            "name": "Certificate",
            "issuer": "Issuer",
            "credentialUrl": "",
            "issuedOn": start,
            "expiresOn": end,
        }
    content[section] = [item]
    if valid:
        ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))
    else:
        with pytest.raises(ValidationError):
            ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))


@pytest.mark.parametrize("date_format", list(ResumeDateFormatEnum))
def test_format_settings_do_not_change_visible_text_limit(
    date_format: ResumeDateFormatEnum,
) -> None:
    projects: list[dict[str, Any]] = [
        {
            "name": "P",
            "role": "",
            "teamSize": "",
            "scale": "",
            "description": "x" * 500,
            "highlights": [],
            "technologies": [],
            "url": "",
        }
        for _ in range(100)
    ]
    projects[-1]["description"] = "x" * 384
    experience = []
    for index in range(0, 100, 15):
        item = experience_payload()
        item.update(
            company="C",
            position="E",
            location="",
            summary="",
            highlights=[],
            technologies=[],
            projects=projects[index : index + 15],
        )
        experience.append(item)
    content = ApiFactoryHelper.resume_content(
        full_name="N",
        role="R",
        summary="",
        experience=experience,
    )
    content["skills"] = []
    content["settings"] = {
        "dateFormat": date_format.value,
        "sectionOrder": [],
        "hiddenSections": [],
    }

    ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))

    projects[-1]["description"] += "x"
    with pytest.raises(ValidationError, match="resume text exceeds limit"):
        ResumeRequestSchema.model_validate(ApiFactoryHelper.resume_request(content=content))
