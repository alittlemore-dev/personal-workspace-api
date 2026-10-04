from dataclasses import dataclass
from datetime import date
from typing import ClassVar, Self

from core.i18n.enums import LanguageEnum
from core.resumes.enums import (
    ResumeCurrentStatusEnum,
    ResumeDateFormatEnum,
    ResumeSectionEnum,
    ResumeThemeEnum,
)
from core.resumes.schemas import (
    ResumeAdditionalSection,
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
    sections: list[ResumeSectionEnum]
    education_sections: list[ResumeAdditionalSection]
    additional_sections: list[ResumeAdditionalSection]

    _SECTION_ORDERS: ClassVar[dict[ResumeThemeEnum, tuple[ResumeSectionEnum, ...]]] = {
        ResumeThemeEnum.SIMPLE: (
            ResumeSectionEnum.SUMMARY,
            ResumeSectionEnum.SKILLS,
            ResumeSectionEnum.EXPERIENCE,
            ResumeSectionEnum.EDUCATION,
            ResumeSectionEnum.CERTIFICATIONS,
            ResumeSectionEnum.LANGUAGES,
            ResumeSectionEnum.ADDITIONAL_SECTIONS,
        ),
        ResumeThemeEnum.ACCENT: (
            ResumeSectionEnum.SUMMARY,
            ResumeSectionEnum.SKILLS,
            ResumeSectionEnum.EDUCATION,
            ResumeSectionEnum.LANGUAGES,
            ResumeSectionEnum.EXPERIENCE,
            ResumeSectionEnum.CERTIFICATIONS,
            ResumeSectionEnum.ADDITIONAL_SECTIONS,
        ),
    }

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
    _MONTH_NAMES_RU: ClassVar[tuple[str, ...]] = (
        "янв.",
        "февр.",
        "мар.",
        "апр.",
        "май",
        "июн.",
        "июл.",
        "авг.",
        "сент.",
        "окт.",
        "нояб.",
        "дек.",
    )

    @classmethod
    def from_params(cls, *, params: ResumeExportParams) -> Self:
        labels = cls._labels_for_language(language=params.language)
        content = params.content.with_resolved_project_roles()
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
        uses_education_fallback = params.theme is ResumeThemeEnum.ACCENT and not content.education
        education_sections = [
            section
            for section in content.additional_sections
            if uses_education_fallback
            and section.title == labels.education
            and ResumeSectionEnum.ADDITIONAL_SECTIONS not in content.settings.hidden_sections
        ]
        return cls(
            title=params.title,
            display_name=profile.full_name or params.title,
            language=params.language,
            labels=labels,
            content=content,
            contacts=[{"label": label, "value": value} for label, value in contacts if value],
            simple_contact_line=" | ".join(part for part in simple_contacts if part),
            sections=[
                section
                for section in content.settings.section_order or cls._SECTION_ORDERS[params.theme]
                if section not in content.settings.hidden_sections
            ],
            education_sections=education_sections,
            additional_sections=[
                section
                for section in content.additional_sections
                if not uses_education_fallback or section.title != labels.education
            ],
            experiences=[
                cls._experience_view(
                    item=item,
                    language=params.language,
                    date_format=content.settings.date_format,
                )
                for item in content.experience
            ],
            educations=[
                cls._education_view(
                    item=item,
                    language=params.language,
                    date_format=content.settings.date_format,
                )
                for item in content.education
            ],
            certifications=[
                cls._certification_view(
                    item=item,
                    language=params.language,
                    date_format=content.settings.date_format,
                    labels=labels,
                )
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
            "sections": self.sections,
            "education_sections": self.education_sections,
            "additional_sections": self.additional_sections,
        }

    @classmethod
    def _experience_view(
        cls,
        *,
        item: ResumeExperienceItem,
        language: LanguageEnum,
        date_format: ResumeDateFormatEnum,
    ) -> ExperienceView:
        period = cls._date_range(
            start_date=item.start_date,
            end_date=item.end_date,
            current_status=item.current_status,
            language=language,
            date_format=date_format,
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
        date_format: ResumeDateFormatEnum,
    ) -> EducationView:
        period = cls._date_range(
            start_date=item.start_date,
            end_date=item.end_date,
            current_status=ResumeCurrentStatusEnum.NOT_SET,
            language=language,
            date_format=date_format,
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
        date_format: ResumeDateFormatEnum,
        labels: ResumeLabels,
    ) -> CertificationView:
        dates = []
        if item.issued_on:
            issued = cls._format_date(
                value=item.issued_on,
                language=language,
                date_format=date_format,
            )
            dates.append(f"{labels.issued}: {issued}")
        if item.expires_on:
            expires = cls._format_date(
                value=item.expires_on,
                language=language,
                date_format=date_format,
            )
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
        date_format: ResumeDateFormatEnum,
    ) -> str:
        start = cls._format_date(value=start_date, language=language, date_format=date_format)
        end = (
            cls._labels_for_language(language=language).present
            if current_status == ResumeCurrentStatusEnum.CURRENT
            else ""
        )
        if not end:
            end = cls._format_date(value=end_date, language=language, date_format=date_format)
        if start and end:
            return f"{start} - {end}"
        return start or end

    @classmethod
    def _format_date(
        cls,
        *,
        value: date | None,
        language: LanguageEnum,
        date_format: ResumeDateFormatEnum,
    ) -> str:
        if value is None:
            return ""
        if date_format is ResumeDateFormatEnum.YEAR:
            return str(value.year)
        if date_format is ResumeDateFormatEnum.MONTH_YEAR_NUMERIC:
            return f"{value.month:02d}.{value.year}"
        if date_format is ResumeDateFormatEnum.FULL_DATE:
            return value.strftime("%d.%m.%Y" if language is LanguageEnum.RU else "%m/%d/%Y")
        months = cls._MONTH_NAMES_RU if language is LanguageEnum.RU else cls._MONTH_NAMES
        return f"{months[value.month - 1]} {value.year}"
