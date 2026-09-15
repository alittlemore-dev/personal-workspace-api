from datetime import date
from typing import Any, Self

from sqlalchemy import Enum, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, declared_attr, mapped_column
from sqlalchemy_dev_utils.mixins.audit import AuditMixin

from core.i18n.enums import LanguageEnum
from core.resumes.enums import ResumeCurrentStatusEnum
from core.resumes.schemas import (
    Resume,
    ResumeAdditionalSection,
    ResumeAdditionalSectionItem,
    ResumeCertificationItem,
    ResumeContent,
    ResumeCreateParams,
    ResumeEducationItem,
    ResumeExperienceItem,
    ResumeLanguageItem,
    ResumeProfile,
    ResumeProjectItem,
    ResumeSkillGroup,
    ResumeSummary,
)
from infra.postgresql.models.base import BaseModel, TableArgs
from infra.postgresql.models.mixins.ids import HexUuidIDMixin


class ResumeModel(HexUuidIDMixin, AuditMixin, BaseModel):
    title: Mapped[str] = mapped_column(String(length=255), doc="Private workspace resume title")
    language: Mapped[LanguageEnum] = mapped_column(
        Enum(LanguageEnum, native_enum=True, name="language_enum"),
        doc="User-selected resume language",
    )
    author_username: Mapped[str] = mapped_column(
        String(length=255),
        doc="Username of the resume author",
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, doc="Structured ATS resume content")

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgs:
        return (
            Index(
                "resumes_resume_author_updated_id_idx",
                cls.author_username,
                cls.updated_at.desc(),
                cls.id.desc(),
            ),
        )

    @classmethod
    def from_create_params(cls, *, params: ResumeCreateParams) -> Self:
        return cls(
            title=params.title,
            language=params.language,
            author_username=params.author_username,
            content=cls._content_to_json(content=params.content),
        )

    @classmethod
    def from_domain_schema(cls, *, resume: Resume) -> Self:
        return cls(
            id=resume.id,
            title=resume.title,
            language=resume.language,
            author_username=resume.author_username,
            content=cls._content_to_json(content=resume.content),
            created_at=resume.created_at,
            updated_at=resume.updated_at,
        )

    def update_from_domain_schema(self, *, resume: Resume) -> None:
        self.title = resume.title
        self.language = resume.language
        self.author_username = resume.author_username
        self.content = self._content_to_json(content=resume.content)
        self.updated_at = resume.updated_at

    def to_domain_schema(self) -> Resume:
        return Resume(
            id=self.id,
            title=self.title,
            language=self.language,
            content=self._content_from_json(data=self.content),
            author_username=self.author_username,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def _content_to_json(cls, *, content: ResumeContent) -> dict[str, Any]:
        return {
            "profile": cls._profile_to_json(profile=content.profile),
            "summary": {
                "text": content.summary.text,
            },
            "skills": [
                {
                    "category": skill.category,
                    "items": list(skill.items),
                }
                for skill in content.skills
            ],
            "experience": [
                cls._experience_to_json(experience=experience) for experience in content.experience
            ],
            "education": [
                cls._education_to_json(education=education) for education in content.education
            ],
            "languages": [
                {
                    "name": language.name,
                    "proficiency": language.proficiency,
                }
                for language in content.languages
            ],
            "certifications": [
                cls._certification_to_json(certification=certification)
                for certification in content.certifications
            ],
            "additional_sections": [
                cls._additional_section_to_json(section=section)
                for section in content.additional_sections
            ],
        }

    @staticmethod
    def _profile_to_json(*, profile: ResumeProfile) -> dict[str, str]:
        return {
            "full_name": profile.full_name,
            "role": profile.role,
            "location": profile.location,
            "email": profile.email,
            "phone": profile.phone,
            "website_url": profile.website_url,
            "linkedin_url": profile.linkedin_url,
            "github_url": profile.github_url,
            "telegram": profile.telegram,
        }

    @classmethod
    def _experience_to_json(cls, *, experience: ResumeExperienceItem) -> dict[str, Any]:
        return {
            "company": experience.company,
            "position": experience.position,
            "location": experience.location,
            "start_date": cls._date_to_json(value=experience.start_date),
            "end_date": cls._date_to_json(value=experience.end_date),
            "current_status": cls._current_status_to_json(value=experience.current_status),
            "summary": experience.summary,
            "highlights": list(experience.highlights),
            "technologies": list(experience.technologies),
            "projects": [cls._project_to_json(project=project) for project in experience.projects],
        }

    @staticmethod
    def _project_to_json(*, project: ResumeProjectItem) -> dict[str, Any]:
        return {
            "name": project.name,
            "role": project.role,
            "description": project.description,
            "highlights": list(project.highlights),
            "technologies": list(project.technologies),
            "url": project.url,
        }

    @classmethod
    def _education_to_json(cls, *, education: ResumeEducationItem) -> dict[str, Any]:
        return {
            "institution": education.institution,
            "degree": education.degree,
            "field": education.field,
            "location": education.location,
            "start_date": cls._date_to_json(value=education.start_date),
            "end_date": cls._date_to_json(value=education.end_date),
            "description": education.description,
        }

    @classmethod
    def _certification_to_json(
        cls,
        *,
        certification: ResumeCertificationItem,
    ) -> dict[str, Any]:
        return {
            "name": certification.name,
            "issuer": certification.issuer,
            "issued_on": cls._date_to_json(value=certification.issued_on),
            "expires_on": cls._date_to_json(value=certification.expires_on),
            "credential_url": certification.credential_url,
        }

    @staticmethod
    def _additional_section_to_json(*, section: ResumeAdditionalSection) -> dict[str, Any]:
        return {
            "title": section.title,
            "items": [
                {
                    "title": item.title,
                    "description": item.description,
                    "url": item.url,
                }
                for item in section.items
            ],
        }

    @classmethod
    def _content_from_json(cls, *, data: dict[str, Any]) -> ResumeContent:
        return ResumeContent(
            profile=cls._profile_from_json(data=data["profile"]),
            summary=ResumeSummary(
                text=cls._string_from_json(value=data["summary"]["text"]),
            ),
            skills=[
                ResumeSkillGroup(
                    category=cls._string_from_json(value=skill["category"]),
                    items=cls._string_list_from_json(value=skill["items"]),
                )
                for skill in cls._list_from_json(value=data["skills"])
            ],
            experience=[
                cls._experience_from_json(data=experience)
                for experience in cls._list_from_json(value=data["experience"])
            ],
            education=[
                cls._education_from_json(data=education)
                for education in cls._list_from_json(value=data["education"])
            ],
            languages=[
                ResumeLanguageItem(
                    name=cls._string_from_json(value=language["name"]),
                    proficiency=cls._string_from_json(value=language["proficiency"]),
                )
                for language in cls._list_from_json(value=data["languages"])
            ],
            certifications=[
                cls._certification_from_json(data=certification)
                for certification in cls._list_from_json(value=data["certifications"])
            ],
            additional_sections=[
                cls._additional_section_from_json(data=section)
                for section in cls._list_from_json(value=data["additional_sections"])
            ],
        )

    @classmethod
    def _profile_from_json(cls, *, data: dict[str, Any]) -> ResumeProfile:
        return ResumeProfile(
            full_name=cls._string_from_json(value=data["full_name"]),
            role=cls._string_from_json(value=data["role"]),
            location=cls._string_from_json(value=data["location"]),
            email=cls._string_from_json(value=data["email"]),
            phone=cls._string_from_json(value=data["phone"]),
            website_url=cls._string_from_json(value=data["website_url"]),
            linkedin_url=cls._string_from_json(value=data["linkedin_url"]),
            github_url=cls._string_from_json(value=data["github_url"]),
            telegram=cls._string_from_json(value=data["telegram"]),
        )

    @classmethod
    def _experience_from_json(cls, *, data: dict[str, Any]) -> ResumeExperienceItem:
        return ResumeExperienceItem(
            company=cls._string_from_json(value=data["company"]),
            position=cls._string_from_json(value=data["position"]),
            location=cls._string_from_json(value=data["location"]),
            start_date=cls._date_from_json(value=data["start_date"]),
            end_date=cls._date_from_json(value=data["end_date"]),
            current_status=cls._current_status_from_json(value=data["current_status"]),
            summary=cls._string_from_json(value=data["summary"]),
            highlights=cls._string_list_from_json(value=data["highlights"]),
            technologies=cls._string_list_from_json(value=data["technologies"]),
            projects=[
                cls._project_from_json(data=project)
                for project in cls._list_from_json(value=data["projects"])
            ],
        )

    @classmethod
    def _project_from_json(cls, *, data: dict[str, Any]) -> ResumeProjectItem:
        return ResumeProjectItem(
            name=cls._string_from_json(value=data["name"]),
            role=cls._string_from_json(value=data["role"]),
            description=cls._string_from_json(value=data["description"]),
            highlights=cls._string_list_from_json(value=data["highlights"]),
            technologies=cls._string_list_from_json(value=data["technologies"]),
            url=cls._string_from_json(value=data["url"]),
        )

    @classmethod
    def _education_from_json(cls, *, data: dict[str, Any]) -> ResumeEducationItem:
        return ResumeEducationItem(
            institution=cls._string_from_json(value=data["institution"]),
            degree=cls._string_from_json(value=data["degree"]),
            field=cls._string_from_json(value=data["field"]),
            location=cls._string_from_json(value=data["location"]),
            start_date=cls._date_from_json(value=data["start_date"]),
            end_date=cls._date_from_json(value=data["end_date"]),
            description=cls._string_from_json(value=data["description"]),
        )

    @classmethod
    def _certification_from_json(cls, *, data: dict[str, Any]) -> ResumeCertificationItem:
        return ResumeCertificationItem(
            name=cls._string_from_json(value=data["name"]),
            issuer=cls._string_from_json(value=data["issuer"]),
            issued_on=cls._date_from_json(value=data["issued_on"]),
            expires_on=cls._date_from_json(value=data["expires_on"]),
            credential_url=cls._string_from_json(value=data["credential_url"]),
        )

    @classmethod
    def _additional_section_from_json(cls, *, data: dict[str, Any]) -> ResumeAdditionalSection:
        return ResumeAdditionalSection(
            title=cls._string_from_json(value=data["title"]),
            items=[
                ResumeAdditionalSectionItem(
                    title=cls._string_from_json(value=item["title"]),
                    description=cls._string_from_json(value=item["description"]),
                    url=cls._string_from_json(value=item["url"]),
                )
                for item in cls._list_from_json(value=data["items"])
            ],
        )

    @staticmethod
    def _string_from_json(*, value: object) -> str:
        return value if isinstance(value, str) else ""

    @staticmethod
    def _list_from_json(*, value: object) -> list[Any]:
        return value if isinstance(value, list) else []

    @classmethod
    def _string_list_from_json(cls, *, value: object) -> list[str]:
        return [cls._string_from_json(value=item) for item in cls._list_from_json(value=value)]

    @staticmethod
    def _current_status_to_json(*, value: ResumeCurrentStatusEnum) -> str:
        return value.value

    @staticmethod
    def _current_status_from_json(*, value: object) -> ResumeCurrentStatusEnum:
        if isinstance(value, str):
            try:
                return ResumeCurrentStatusEnum(value)
            except ValueError:
                return ResumeCurrentStatusEnum.NOT_SET
        return ResumeCurrentStatusEnum.NOT_SET

    @staticmethod
    def _date_to_json(*, value: date | None) -> str | None:
        return value.isoformat() if value is not None else None

    @staticmethod
    def _date_from_json(*, value: str | None) -> date | None:
        return date.fromisoformat(value) if value is not None else None
