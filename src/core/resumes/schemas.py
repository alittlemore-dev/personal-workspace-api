from dataclasses import dataclass
from datetime import date, datetime
from math import ceil
from typing import Self

from core.i18n.enums import LanguageEnum
from core.resumes.enums import ResumeCurrentStatusEnum, ResumeExportFormatEnum
from core.schemas import ValuedDataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeProfile:
    full_name: str
    role: str
    location: str
    email: str
    phone: str
    website_url: str
    linkedin_url: str
    github_url: str
    telegram: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeSummary:
    text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeSkillGroup:
    category: str
    items: list[str]


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeProjectItem:
    name: str
    role: str
    description: str
    highlights: list[str]
    technologies: list[str]
    url: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeExperienceItem:
    company: str
    position: str
    location: str
    start_date: date | None
    end_date: date | None
    current_status: ResumeCurrentStatusEnum
    summary: str
    highlights: list[str]
    technologies: list[str]
    projects: list[ResumeProjectItem]


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeEducationItem:
    institution: str
    degree: str
    field: str
    location: str
    start_date: date | None
    end_date: date | None
    description: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeLanguageItem:
    name: str
    proficiency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeCertificationItem:
    name: str
    issuer: str
    issued_on: date | None
    expires_on: date | None
    credential_url: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeAdditionalSectionItem:
    title: str
    description: str
    url: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeAdditionalSection:
    title: str
    items: list[ResumeAdditionalSectionItem]


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeContent:
    profile: ResumeProfile
    summary: ResumeSummary
    skills: list[ResumeSkillGroup]
    experience: list[ResumeExperienceItem]
    education: list[ResumeEducationItem]
    languages: list[ResumeLanguageItem]
    certifications: list[ResumeCertificationItem]
    additional_sections: list[ResumeAdditionalSection]


@dataclass(frozen=True, slots=True, kw_only=True)
class Resume:
    id: str
    title: str
    language: LanguageEnum
    content: ResumeContent
    author_username: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class Resumes(ValuedDataclass[Resume]):
    total_count: int
    total_pages: int

    @classmethod
    def from_page(cls, *, values: list[Resume], total_count: int, page_size: int) -> Self:
        return cls(
            values=values,
            total_count=total_count,
            total_pages=ceil(total_count / page_size) if total_count > 0 else 0,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeFilters:
    page: int | None
    page_size: int | None
    search_query: str | None
    author_username: str

    @property
    def limit(self) -> int:
        if self.page_size is None:
            raise ValueError
        return self.page_size

    @property
    def offset(self) -> int:
        if self.page is None or self.page_size is None:
            raise ValueError
        return (self.page - 1) * self.page_size


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeCreateParams:
    title: str
    language: LanguageEnum
    content: ResumeContent
    author_username: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeUpdateParams:
    title: str
    language: LanguageEnum
    content: ResumeContent

    def to_resume(self, *, existing_resume: Resume, now: datetime) -> Resume:
        return Resume(
            id=existing_resume.id,
            title=self.title,
            language=self.language,
            content=self.content,
            author_username=existing_resume.author_username,
            created_at=existing_resume.created_at,
            updated_at=now,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeExportParams:
    format: ResumeExportFormatEnum
    title: str
    language: LanguageEnum
    content: ResumeContent


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeExport:
    format: ResumeExportFormatEnum
    content: bytes
