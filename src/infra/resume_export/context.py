from dataclasses import dataclass
from datetime import date
from typing import ClassVar, Self

from core.i18n.enums import LanguageEnum
from core.resumes.enums import ResumeCurrentStatusEnum
from core.resumes.schemas import (
    ResumeCertificationItem,
    ResumeContent,
    ResumeEducationItem,
    ResumeExperienceItem,
    ResumeExportParams,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeLabels:
    summary: str
    skills: str
    experience: str
    project: str
    education: str
    languages: str
    certifications: str
    present: str
    technologies: str
    issued: str
    expires: str
    phone: str
    website: str
    team_size: str
    scale: str
    contacts: str
    footer: str
    page: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ExperienceView:
    item: ResumeExperienceItem
    period: str
    position_location: str
    location_period: str


@dataclass(frozen=True, slots=True, kw_only=True)
class EducationView:
    item: ResumeEducationItem
    period: str
    details: str
    location_period: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CertificationView:
    item: ResumeCertificationItem
    dates: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeTemplateContext:
    title: str
    display_name: str
    language: LanguageEnum
    labels: ResumeLabels
    content: ResumeContent
    contacts: list[dict[str, str]]
    simple_contact_line: str
    experiences: list[ExperienceView]
    educations: list[EducationView]
    certifications: list[CertificationView]

    _MONTH_NAMES: ClassVar[tuple[str, ...]] = (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )

    @classmethod
    def from_params(cls, *, params: ResumeExportParams) -> Self:
        labels = cls._labels_for_language(language=params.language)
        content = params.content
        profile = content.profile
        contacts = (
            (labels.phone, profile.phone),
            ("Email", profile.email),
            ("Telegram", profile.telegram),
            ("LinkedIn", profile.linkedin_url),
            ("GitHub", profile.github_url),
            (labels.website, profile.website_url),
        )
        simple_contacts = (
            profile.location,
            profile.email,
            profile.phone,
            profile.website_url,
            profile.linkedin_url,
            profile.github_url,
            profile.telegram,
        )
        return cls(
            title=params.title,
            display_name=profile.full_name or params.title,
            language=params.language,
            labels=labels,
            content=content,
            contacts=[{"label": label, "value": value} for label, value in contacts if value],
            simple_contact_line=" | ".join(part for part in simple_contacts if part),
            experiences=[
                cls._experience_view(item=item, language=params.language, present=labels.present)
                for item in content.experience
            ],
            educations=[
                cls._education_view(item=item, language=params.language, present=labels.present)
                for item in content.education
            ],
            certifications=[
                cls._certification_view(item=item, language=params.language, labels=labels)
                for item in content.certifications
            ],
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "display_name": self.display_name,
            "language": self.language.value,
            "labels": self.labels,
            "content": self.content,
            "contacts": self.contacts,
            "simple_contact_line": self.simple_contact_line,
            "experiences": self.experiences,
            "educations": self.educations,
            "certifications": self.certifications,
        }

    @classmethod
    def _experience_view(
        cls,
        *,
        item: ResumeExperienceItem,
        language: LanguageEnum,
        present: str,
    ) -> ExperienceView:
        period = cls._date_range(
            start_date=item.start_date,
            end_date=item.end_date,
            current_status=item.current_status,
            language=language,
            present=present,
        )
        return ExperienceView(
            item=item,
            period=period,
            position_location=" | ".join(part for part in (item.position, item.location) if part),
            location_period=" | ".join(part for part in (item.location, period) if part),
        )

    @classmethod
    def _education_view(
        cls,
        *,
        item: ResumeEducationItem,
        language: LanguageEnum,
        present: str,
    ) -> EducationView:
        period = cls._date_range(
            start_date=item.start_date,
            end_date=item.end_date,
            current_status=ResumeCurrentStatusEnum.NOT_SET,
            language=language,
            present=present,
        )
        return EducationView(
            item=item,
            period=period,
            details=" | ".join(part for part in (item.degree, item.field) if part),
            location_period=" | ".join(part for part in (item.location, period) if part),
        )

    @classmethod
    def _certification_view(
        cls,
        *,
        item: ResumeCertificationItem,
        language: LanguageEnum,
        labels: ResumeLabels,
    ) -> CertificationView:
        dates = []
        if item.issued_on:
            issued = cls._format_date(value=item.issued_on, language=language)
            dates.append(f"{labels.issued}: {issued}")
        if item.expires_on:
            expires = cls._format_date(value=item.expires_on, language=language)
            dates.append(f"{labels.expires}: {expires}")
        return CertificationView(item=item, dates=" | ".join(dates))

    @classmethod
    def _labels_for_language(cls, *, language: LanguageEnum) -> ResumeLabels:
        if language == LanguageEnum.RU:
            return ResumeLabels(
                summary="Профессиональный профиль",
                skills="Навыки",
                experience="Опыт работы",
                project="Проект",
                education="Образование",
                languages="Языки",
                certifications="Сертификаты",
                present="настоящее время",
                technologies="Технологии",
                issued="Выдан",
                expires="Истекает",
                phone="Телефон",
                website="Сайт",
                team_size="Размер команды",
                scale="Масштаб и нагрузка",
                contacts="Контактные данные",
                footer="Резюме",
                page="Страница",
            )
        return ResumeLabels(
            summary="Professional Summary",
            skills="Skills",
            experience="Work Experience",
            project="Project",
            education="Education",
            languages="Languages",
            certifications="Certifications",
            present="Present",
            technologies="Technologies",
            issued="Issued",
            expires="Expires",
            phone="Phone",
            website="Website",
            team_size="Team size",
            scale="Scale and load",
            contacts="Contacts",
            footer="Resume",
            page="Page",
        )

    @classmethod
    def _date_range(
        cls,
        *,
        start_date: date | None,
        end_date: date | None,
        current_status: ResumeCurrentStatusEnum,
        language: LanguageEnum,
        present: str,
    ) -> str:
        start = cls._format_date(value=start_date, language=language)
        end = present if current_status == ResumeCurrentStatusEnum.CURRENT else ""
        if not end:
            end = cls._format_date(value=end_date, language=language)
        if start and end:
            return f"{start} - {end}"
        return start or end

    @classmethod
    def _format_date(cls, *, value: date | None, language: LanguageEnum) -> str:
        if value is None:
            return ""
        if language == LanguageEnum.RU:
            return f"{value.month:02d}.{value.year}"
        return f"{cls._MONTH_NAMES[value.month - 1]} {value.year}"
