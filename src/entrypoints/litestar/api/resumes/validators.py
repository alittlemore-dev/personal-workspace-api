from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING, Annotated

from pydantic import AfterValidator

from core.resumes.enums import ResumeCurrentStatusEnum
from entrypoints.litestar.api.resumes.limits import ResumeLimits
from entrypoints.litestar.api.validation import ShortText

if TYPE_CHECKING:
    from entrypoints.litestar.api.resumes.schemas import (
        ResumeCertificationItemSchema,
        ResumeContentSchema,
        ResumeEducationItemSchema,
        ResumeExperienceItemSchema,
        ResumeProjectItemSchema,
        ResumeSkillGroupSchema,
    )

ResumeOptionalShortText = Annotated[ShortText, AfterValidator(str.strip)]


def require_unique(values: Iterable[str], *, label: str) -> None:
    normalized = [" ".join(value.split()).casefold() for value in values]
    if len(normalized) != len(set(normalized)):
        message = f"duplicate {label}"
        raise ValueError(message)


def validate_resume_phone(value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        return ""
    phone_pattern = r"\+?[0-9 ()/.\-]+(?:\s*(?:ext\.?|x)\s*\d{1,6})?"
    if re.fullmatch(phone_pattern, trimmed, re.IGNORECASE) is None:
        message = "phone contains unsupported characters"
        raise ValueError(message)
    digits = sum(character.isdigit() for character in trimmed)
    if digits < ResumeLimits.phone_min_digits or digits > ResumeLimits.phone_max_digits:
        message = "phone must contain 7 to 20 digits"
        raise ValueError(message)
    return trimmed


def visible_text_length(value: object) -> int:
    if isinstance(value, str):
        return len(value.strip())
    if isinstance(value, list):
        return sum(visible_text_length(item) for item in value)
    if isinstance(value, dict):
        return sum(
            visible_text_length(item)
            for key, item in value.items()
            if isinstance(key, str) and not key.endswith("url") and key != "current_status"
        )
    return 0


def validate_unique_skill_items(value: ResumeSkillGroupSchema) -> ResumeSkillGroupSchema:
    require_unique(value.items, label="skills")
    return value


def validate_project_content(value: ResumeProjectItemSchema) -> ResumeProjectItemSchema:
    if not value.description.strip() and not value.highlights:
        message = "project requires a description or highlight"
        raise ValueError(message)
    require_unique(value.technologies, label="project technologies")
    return value


def validate_experience_content(value: ResumeExperienceItemSchema) -> ResumeExperienceItemSchema:
    if not value.summary.strip() and not value.highlights and not value.projects:
        message = "experience requires a summary, highlight or project"
        raise ValueError(message)
    if value.end_date is not None and value.end_date < value.start_date:
        message = "experience end date must not precede start date"
        raise ValueError(message)
    if value.current_status is ResumeCurrentStatusEnum.CURRENT and value.end_date is not None:
        message = "current experience must not have an end date"
        raise ValueError(message)
    require_unique(value.technologies, label="experience technologies")
    return value


def validate_education_dates(value: ResumeEducationItemSchema) -> ResumeEducationItemSchema:
    if value.end_date is not None and value.end_date < value.start_date:
        message = "education end date must not precede start date"
        raise ValueError(message)
    return value


def validate_certification_dates(
    value: ResumeCertificationItemSchema,
) -> ResumeCertificationItemSchema:
    if (
        value.issued_on is not None
        and value.expires_on is not None
        and value.expires_on < value.issued_on
    ):
        message = "certification expiration must not precede issue date"
        raise ValueError(message)
    return value


def validate_resume_totals(value: ResumeContentSchema) -> ResumeContentSchema:
    if sum(len(group.items) for group in value.skills) > ResumeLimits.skills_total:
        message = "too many skills in resume"
        raise ValueError(message)
    if sum(len(item.projects) for item in value.experience) > ResumeLimits.projects_total:
        message = "too many projects in resume"
        raise ValueError(message)
    if (
        sum(len(section.items) for section in value.additional_sections)
        > ResumeLimits.additional_items_total
    ):
        message = "too many additional items in resume"
        raise ValueError(message)
    require_unique((group.category for group in value.skills), label="skill categories")
    require_unique((item.name for item in value.languages), label="languages")
    require_unique((section.title for section in value.additional_sections), label="section titles")
    if visible_text_length(value.model_dump()) > ResumeLimits.visible_text:
        message = "resume text exceeds limit"
        raise ValueError(message)
    return value
