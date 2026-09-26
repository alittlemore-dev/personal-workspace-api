from copy import deepcopy
from io import BytesIO
from typing import Any

import pytest
from pydantic import ValidationError
from pypdf import PdfWriter

from core.resumes.enums import ResumeExportFormatEnum
from core.resumes.schemas import ResumeExport
from entrypoints.litestar.api.resumes.responses import ResumeExportResponse
from entrypoints.litestar.api.resumes.schemas import ResumeRequestSchema
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
