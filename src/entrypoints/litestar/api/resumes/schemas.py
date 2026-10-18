from datetime import date
from typing import Annotated, Self, cast

from litestar.datastructures.upload_file import UploadFile
from pydantic import AfterValidator, ConfigDict, Field, model_validator

from core.i18n.enums import LanguageEnum
from core.resumes.enums import (
    ResumeCurrentStatusEnum,
    ResumeDateFormatEnum,
    ResumeExportFormatEnum,
    ResumeSectionEnum,
    ResumeThemeEnum,
)
from core.resumes.schemas import (
    Resume,
    ResumeAdditionalSection,
    ResumeAdditionalSectionItem,
    ResumeCertificationItem,
    ResumeContent,
    ResumeCreateParams,
    ResumeEducationItem,
    ResumeExperienceItem,
    ResumeExportParams,
    ResumeLanguageItem,
    ResumeProfile,
    ResumeProjectItem,
    Resumes,
    ResumeSettings,
    ResumeSkillGroup,
    ResumeSummary,
    ResumeUpdateParams,
)
from entrypoints.litestar.api.resumes.limits import ResumeLimits
from entrypoints.litestar.api.resumes.validators import (
    ResumeOptionalShortText,
    validate_certification_dates,
    validate_education_dates,
    validate_experience_content,
    validate_project_content,
    validate_resume_phone,
    validate_resume_sections,
    validate_resume_totals,
    validate_unique_skill_items,
)
from entrypoints.litestar.api.schemas import CamelCaseSchema
from entrypoints.litestar.api.validation import (
    BlankableEmailString,
    BlankableHttpUrlString,
    RequiredResumeLongText,
    RequiredShortText,
    ResumeLongText,
)


class ResumeProfileSchema(CamelCaseSchema):
    full_name: Annotated[
        RequiredShortText,
        Field(
            title="Full name",
            description="Name printed on the resume.",
            examples=["Alex Morgan"],
        ),
    ]
    photo_file_id: Annotated[
        str,
        Field(
            title="Photo file ID",
            max_length=32,
            pattern=r"^(?:[0-9a-f]{32})?$",
            description="Managed resume photo identifier; an empty string means no photo.",
            examples=[""],
        ),
    ]
    role: Annotated[
        RequiredShortText,
        Field(
            title="Role",
            description="Professional role displayed on the resume.",
            examples=["Backend Engineer"],
        ),
    ]
    location: Annotated[
        ResumeOptionalShortText,
        Field(
            title="Location",
            description="City and country shown on the resume.",
            examples=["Yerevan, Armenia"],
        ),
    ]
    email: Annotated[
        BlankableEmailString,
        Field(
            title="Email",
            description="Contact email; an empty string means it is not provided.",
            examples=["alex.morgan@example.com"],
        ),
    ]
    phone: Annotated[
        str,
        Field(
            title="Phone",
            max_length=64,
            description="Contact phone number; an empty string means it is not provided.",
            examples=["+12025550123"],
        ),
        AfterValidator(validate_resume_phone),
    ]
    website_url: Annotated[
        BlankableHttpUrlString,
        Field(
            title="Website URL",
            description="Personal website URL; an empty string means it is not provided.",
            examples=["https://alex.example.com"],
        ),
    ]
    linkedin_url: Annotated[
        BlankableHttpUrlString,
        Field(
            title="LinkedIn URL",
            description="LinkedIn profile URL; an empty string means it is not provided.",
            examples=["https://www.linkedin.com/in/alex-morgan"],
        ),
    ]
    github_url: Annotated[
        BlankableHttpUrlString,
        Field(
            title="GitHub URL",
            description="GitHub profile URL; an empty string means it is not provided.",
            examples=["https://github.com/alex-morgan"],
        ),
    ]
    telegram: Annotated[
        ResumeOptionalShortText,
        Field(
            title="Telegram",
            description="Telegram username; an empty string means it is not provided.",
            examples=["@alex_morgan"],
        ),
    ]

    def to_domain_schema(self) -> ResumeProfile:
        return ResumeProfile(
            full_name=self.full_name,
            photo_file_id=self.photo_file_id,
            role=self.role,
            location=self.location,
            email=self.email,
            phone=self.phone,
            website_url=self.website_url,
            linkedin_url=self.linkedin_url,
            github_url=self.github_url,
            telegram=self.telegram,
        )

    @classmethod
    def from_domain_schema(cls, *, schema: ResumeProfile) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                full_name=schema.full_name,
                photo_file_id=schema.photo_file_id,
                role=schema.role,
                location=schema.location,
                email=schema.email,
                phone=schema.phone,
                website_url=schema.website_url,
                linkedin_url=schema.linkedin_url,
                github_url=schema.github_url,
                telegram=schema.telegram,
            ),
        )


class ResumePhotoUploadRequestSchema(CamelCaseSchema):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    file: Annotated[
        UploadFile,
        Field(
            title="Resume photo",
            description=(
                "Binary file part in multipart/form-data; select a local file, not a JSON filename."
            ),
        ),
    ]


class ResumeSummarySchema(CamelCaseSchema):
    text: Annotated[
        ResumeLongText,
        Field(
            title="Summary",
            max_length=ResumeLimits.summary,
            description="Plain text content.",
            examples=["Built reliable APIs for product teams."],
        ),
    ]

    def to_domain_schema(self) -> ResumeSummary:
        return ResumeSummary(text=self.text)

    @classmethod
    def from_domain_schema(cls, *, schema: ResumeSummary) -> Self:
        return cast("Self", cls.model_construct(text=schema.text))


class ResumeSkillGroupSchema(CamelCaseSchema):
    category: Annotated[
        RequiredShortText,
        Field(
            title="Skill category",
            description="Skill group label.",
            examples=["Backend development"],
        ),
    ]
    items: Annotated[
        list[RequiredShortText],
        Field(
            title="Skill items",
            min_length=1,
            max_length=ResumeLimits.skills_per_group,
            description="Unique skill names within this group.",
            examples=[["Python", "SQL"]],
        ),
    ]

    validate_unique_items = model_validator(mode="after")(validate_unique_skill_items)

    def to_domain_schema(self) -> ResumeSkillGroup:
        return ResumeSkillGroup(
            category=self.category,
            items=list(self.items),
        )

    @classmethod
    def from_domain_schema(cls, *, schema: ResumeSkillGroup) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                category=schema.category,
                items=list(schema.items),
            ),
        )


class ResumeProjectItemSchema(CamelCaseSchema):
    name: Annotated[
        RequiredShortText,
        Field(
            title="Project name",
            description="Project or product name.",
            examples=["Payments platform"],
        ),
    ]
    role: Annotated[
        ResumeOptionalShortText,
        Field(
            title="Project role",
            description="Professional role displayed on the resume.",
            examples=["Backend Engineer"],
        ),
    ]
    team_size: Annotated[
        ResumeOptionalShortText,
        Field(
            title="Team size",
            description="Team size as a short display label.",
            examples=["6 engineers"],
        ),
    ]
    scale: Annotated[
        ResumeOptionalShortText,
        Field(
            title="Project scale",
            description="Short description of project scale.",
            examples=["50,000 daily users"],
        ),
    ]
    description: Annotated[
        ResumeLongText,
        Field(
            title="Project description",
            max_length=ResumeLimits.project_description,
            description="Human-readable description.",
            examples=["Designed APIs and reduced request latency by 30%."],
        ),
    ]
    highlights: Annotated[
        list[Annotated[RequiredResumeLongText, Field(max_length=ResumeLimits.highlight)]],
        Field(
            title="Highlights",
            max_length=ResumeLimits.project_highlights,
            description="Selected achievements and measurable outcomes.",
            examples=[["Reduced API latency by 30%."]],
        ),
    ]
    technologies: Annotated[
        list[RequiredShortText],
        Field(
            title="Technologies",
            max_length=ResumeLimits.project_technologies,
            description="Technologies used in this role or project.",
            examples=[["Python", "PostgreSQL"]],
        ),
    ]
    url: Annotated[
        BlankableHttpUrlString,
        Field(
            title="Project URL",
            description=("Related absolute HTTP(S) URL; an empty string means it is not provided."),
            examples=["https://example.com/projects/platform"],
        ),
    ]

    validate_content = model_validator(mode="after")(validate_project_content)

    def to_domain_schema(self) -> ResumeProjectItem:
        return ResumeProjectItem(
            name=self.name,
            role=self.role,
            team_size=self.team_size,
            scale=self.scale,
            description=self.description,
            highlights=list(self.highlights),
            technologies=list(self.technologies),
            url=self.url,
        )

    @classmethod
    def from_domain_schema(cls, *, schema: ResumeProjectItem) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                name=schema.name,
                role=schema.role,
                team_size=schema.team_size,
                scale=schema.scale,
                description=schema.description,
                highlights=list(schema.highlights),
                technologies=list(schema.technologies),
                url=schema.url,
            ),
        )


class ResumeExperienceItemSchema(CamelCaseSchema):
    company: Annotated[
        RequiredShortText,
        Field(
            title="Company",
            description="Employer or organization name.",
            examples=["Example Labs"],
        ),
    ]
    company_website_url: Annotated[
        BlankableHttpUrlString,
        Field(
            title="Company website URL",
            description="Employer website URL; an empty string means it is not provided.",
            examples=["https://example.com"],
        ),
    ]
    position: Annotated[
        RequiredShortText,
        Field(title="Position", description="Job title.", examples=["Senior Backend Engineer"]),
    ]
    location: Annotated[
        ResumeOptionalShortText,
        Field(
            title="Location",
            description="City and country shown on the resume.",
            examples=["Yerevan, Armenia"],
        ),
    ]
    start_date: Annotated[
        date | None,
        Field(
            title="Start date",
            description="Start date; null when unknown.",
            examples=["2022-03-01"],
        ),
    ]
    end_date: Annotated[
        date | None,
        Field(
            title="End date",
            description="End date; null when unknown or ongoing.",
            examples=["2025-09-30"],
        ),
    ]
    current_status: Annotated[
        ResumeCurrentStatusEnum,
        Field(
            title="Current status",
            description=(
                "Current status; allowed values are listed in the referenced enumeration."
            ),
            examples=["notCurrent"],
        ),
    ]
    summary: Annotated[
        ResumeLongText,
        Field(
            title="Experience summary",
            max_length=ResumeLimits.experience_summary,
            description="Summary of responsibilities and achievements.",
            examples=["Designed and maintained reliable backend services."],
        ),
    ]
    highlights: Annotated[
        list[Annotated[RequiredResumeLongText, Field(max_length=ResumeLimits.highlight)]],
        Field(
            title="Highlights",
            max_length=ResumeLimits.experience_highlights,
            description="Selected achievements and measurable outcomes.",
            examples=[["Reduced API latency by 30%."]],
        ),
    ]
    technologies: Annotated[
        list[RequiredShortText],
        Field(
            title="Technologies",
            max_length=ResumeLimits.experience_technologies,
            description="Technologies used in this role or project.",
            examples=[["Python", "PostgreSQL"]],
        ),
    ]
    projects: Annotated[
        list[ResumeProjectItemSchema],
        Field(
            title="Experience projects",
            max_length=ResumeLimits.projects_per_experience,
            description="Projects included in this request.",
        ),
    ]

    validate_content = model_validator(mode="after")(validate_experience_content)

    def to_domain_schema(self) -> ResumeExperienceItem:
        return ResumeExperienceItem(
            company=self.company,
            company_website_url=self.company_website_url,
            position=self.position,
            location=self.location,
            start_date=self.start_date,
            end_date=self.end_date,
            current_status=self.current_status,
            summary=self.summary,
            highlights=list(self.highlights),
            technologies=list(self.technologies),
            projects=[project.to_domain_schema() for project in self.projects],
        )

    @classmethod
    def from_domain_schema(cls, *, schema: ResumeExperienceItem) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                company=schema.company,
                company_website_url=schema.company_website_url,
                position=schema.position,
                location=schema.location,
                start_date=schema.start_date,
                end_date=schema.end_date,
                current_status=schema.current_status,
                summary=schema.summary,
                highlights=list(schema.highlights),
                technologies=list(schema.technologies),
                projects=[
                    ResumeProjectItemSchema.from_domain_schema(schema=project)
                    for project in schema.projects
                ],
            ),
        )


class ResumeEducationItemSchema(CamelCaseSchema):
    institution: Annotated[
        RequiredShortText,
        Field(
            title="Institution",
            description="Educational institution.",
            examples=["Example University"],
        ),
    ]
    degree: Annotated[
        RequiredShortText,
        Field(
            title="Degree",
            description="Degree or qualification.",
            examples=["Bachelor of Science"],
        ),
    ]
    field: Annotated[
        RequiredShortText,
        Field(title="Field", description="Field of study.", examples=["Computer Science"]),
    ]
    location: Annotated[
        RequiredShortText,
        Field(
            title="Location",
            description="City and country shown on the resume.",
            examples=["Yerevan, Armenia"],
        ),
    ]
    start_date: Annotated[
        date | None,
        Field(
            title="Start date",
            description="Start date; null when unknown.",
            examples=["2022-03-01"],
        ),
    ]
    end_date: Annotated[
        date | None,
        Field(
            title="End date",
            description="End date; null when unknown or ongoing.",
            examples=["2025-09-30"],
        ),
    ]
    description: Annotated[
        ResumeLongText,
        Field(
            title="Description",
            max_length=ResumeLimits.education_description,
            description="Human-readable description.",
            examples=["Designed APIs and reduced request latency by 30%."],
        ),
    ]

    validate_dates = model_validator(mode="after")(validate_education_dates)

    def to_domain_schema(self) -> ResumeEducationItem:
        return ResumeEducationItem(
            institution=self.institution,
            degree=self.degree,
            field=self.field,
            location=self.location,
            start_date=self.start_date,
            end_date=self.end_date,
            description=self.description,
        )

    @classmethod
    def from_domain_schema(cls, *, schema: ResumeEducationItem) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                institution=schema.institution,
                degree=schema.degree,
                field=schema.field,
                location=schema.location,
                start_date=schema.start_date,
                end_date=schema.end_date,
                description=schema.description,
            ),
        )


class ResumeLanguageItemSchema(CamelCaseSchema):
    name: Annotated[
        RequiredShortText,
        Field(title="Language", description="Language name.", examples=["English"]),
    ]
    proficiency: Annotated[
        RequiredShortText,
        Field(
            title="Proficiency",
            description="Language proficiency as a display label.",
            examples=["Professional working proficiency"],
        ),
    ]

    def to_domain_schema(self) -> ResumeLanguageItem:
        return ResumeLanguageItem(
            name=self.name,
            proficiency=self.proficiency,
        )

    @classmethod
    def from_domain_schema(cls, *, schema: ResumeLanguageItem) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                name=schema.name,
                proficiency=schema.proficiency,
            ),
        )


class ResumeCertificationItemSchema(CamelCaseSchema):
    name: Annotated[
        RequiredShortText,
        Field(
            title="Certification",
            description="Certification or qualification name.",
            examples=["Cloud Developer Certificate"],
        ),
    ]
    issuer: Annotated[
        ResumeOptionalShortText,
        Field(
            title="Issuer",
            description="Organization that issued the certification.",
            examples=["Example Academy"],
        ),
    ]
    issued_on: Annotated[
        date | None,
        Field(
            title="Issued on",
            description="Certificate issue date; null when unknown.",
            examples=["2025-04-15"],
        ),
    ]
    expires_on: Annotated[
        date | None,
        Field(
            title="Expires on",
            description=(
                "Certificate expiry date; null when it does not expire or the date is unknown."
            ),
            examples=[None],
        ),
    ]
    credential_url: Annotated[
        BlankableHttpUrlString,
        Field(
            title="Credential URL",
            description=("Certificate verification URL; an empty string means it is not provided."),
            examples=["https://example.com/certificates/backend"],
        ),
    ]

    validate_dates = model_validator(mode="after")(validate_certification_dates)

    def to_domain_schema(self) -> ResumeCertificationItem:
        return ResumeCertificationItem(
            name=self.name,
            issuer=self.issuer,
            issued_on=self.issued_on,
            expires_on=self.expires_on,
            credential_url=self.credential_url,
        )

    @classmethod
    def from_domain_schema(cls, *, schema: ResumeCertificationItem) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                name=schema.name,
                issuer=schema.issuer,
                issued_on=schema.issued_on,
                expires_on=schema.expires_on,
                credential_url=schema.credential_url,
            ),
        )


class ResumeAdditionalSectionItemSchema(CamelCaseSchema):
    title: Annotated[
        RequiredShortText,
        Field(
            title="Title",
            description="Heading of this entry in the additional section.",
            examples=["Open-source contributions"],
        ),
    ]
    description: Annotated[
        ResumeLongText,
        Field(
            title="Description",
            max_length=ResumeLimits.additional_description,
            description="Human-readable description.",
            examples=["Designed APIs and reduced request latency by 30%."],
        ),
    ]
    url: Annotated[
        BlankableHttpUrlString,
        Field(
            title="URL",
            description=("Related absolute HTTP(S) URL; an empty string means it is not provided."),
            examples=["https://example.com/projects/platform"],
        ),
    ]

    def to_domain_schema(self) -> ResumeAdditionalSectionItem:
        return ResumeAdditionalSectionItem(
            title=self.title,
            description=self.description,
            url=self.url,
        )

    @classmethod
    def from_domain_schema(cls, *, schema: ResumeAdditionalSectionItem) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                title=schema.title,
                description=schema.description,
                url=schema.url,
            ),
        )


class ResumeAdditionalSectionSchema(CamelCaseSchema):
    title: Annotated[
        RequiredShortText,
        Field(
            title="Section title",
            description="Heading of the additional resume section.",
            examples=["Community work"],
        ),
    ]
    items: Annotated[
        list[ResumeAdditionalSectionItemSchema],
        Field(
            title="Section items",
            min_length=1,
            max_length=ResumeLimits.additional_items_per_section,
            description="Items included in this request.",
        ),
    ]

    def to_domain_schema(self) -> ResumeAdditionalSection:
        return ResumeAdditionalSection(
            title=self.title,
            items=[item.to_domain_schema() for item in self.items],
        )

    @classmethod
    def from_domain_schema(cls, *, schema: ResumeAdditionalSection) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                title=schema.title,
                items=[
                    ResumeAdditionalSectionItemSchema.from_domain_schema(schema=item)
                    for item in schema.items
                ],
            ),
        )


class ResumeSettingsSchema(CamelCaseSchema):
    date_format: Annotated[
        ResumeDateFormatEnum,
        Field(
            title="Date format",
            description="Date format; allowed values are listed in the referenced enumeration.",
            examples=["monthYear"],
        ),
    ]
    section_order: Annotated[
        list[ResumeSectionEnum],
        Field(
            title="Section order",
            description="Display order of built-in resume sections.",
            examples=[
                [
                    "summary",
                    "skills",
                    "experience",
                    "education",
                    "languages",
                    "certifications",
                    "additionalSections",
                ],
            ],
        ),
    ]
    hidden_sections: Annotated[
        list[ResumeSectionEnum],
        Field(
            title="Hidden sections",
            description="Built-in resume sections omitted from rendering.",
            examples=[[]],
        ),
    ]

    validate_sections = model_validator(mode="after")(validate_resume_sections)

    def to_domain_schema(self) -> ResumeSettings:
        return ResumeSettings(
            date_format=self.date_format,
            section_order=list(self.section_order),
            hidden_sections=list(self.hidden_sections),
        )

    @classmethod
    def from_domain_schema(cls, *, schema: ResumeSettings) -> Self:
        return cls(
            date_format=schema.date_format,
            section_order=list(schema.section_order),
            hidden_sections=list(schema.hidden_sections),
        )


class ResumeContentSchema(CamelCaseSchema):
    settings: Annotated[
        ResumeSettingsSchema,
        Field(
            title="Resume settings",
            description=("Settings; see the nested schema for its fields."),
        ),
    ]
    profile: Annotated[
        ResumeProfileSchema,
        Field(title="Profile", description="Profile; see the nested schema for its fields."),
    ]
    summary: Annotated[
        ResumeSummarySchema,
        Field(
            title="Summary",
            description="Summary of responsibilities and achievements.",
            examples=[{"text": "Designed and maintained reliable backend services."}],
        ),
    ]
    skills: Annotated[
        list[ResumeSkillGroupSchema],
        Field(
            title="Skills",
            max_length=ResumeLimits.skill_groups,
            description="Skills included in this request.",
        ),
    ]
    experience: Annotated[
        list[ResumeExperienceItemSchema],
        Field(
            title="Experience",
            max_length=ResumeLimits.experience,
            description="Experience included in this request.",
        ),
    ]
    education: Annotated[
        list[ResumeEducationItemSchema],
        Field(
            title="Education",
            max_length=ResumeLimits.education,
            description="Education included in this request.",
        ),
    ]
    languages: Annotated[
        list[ResumeLanguageItemSchema],
        Field(
            title="Languages",
            max_length=ResumeLimits.languages,
            description="Languages included in this request.",
        ),
    ]
    certifications: Annotated[
        list[ResumeCertificationItemSchema],
        Field(
            title="Certifications",
            max_length=ResumeLimits.certifications,
            description="Certifications included in this request.",
        ),
    ]
    additional_sections: Annotated[
        list[ResumeAdditionalSectionSchema],
        Field(
            title="Additional sections",
            max_length=ResumeLimits.additional_sections,
            description="Additional sections included in this request.",
        ),
    ]

    validate_totals = model_validator(mode="after")(validate_resume_totals)

    def to_domain_schema(self) -> ResumeContent:
        return ResumeContent(
            settings=self.settings.to_domain_schema(),
            profile=self.profile.to_domain_schema(),
            summary=self.summary.to_domain_schema(),
            skills=[skill.to_domain_schema() for skill in self.skills],
            experience=[experience.to_domain_schema() for experience in self.experience],
            education=[education.to_domain_schema() for education in self.education],
            languages=[language.to_domain_schema() for language in self.languages],
            certifications=[
                certification.to_domain_schema() for certification in self.certifications
            ],
            additional_sections=[
                section.to_domain_schema() for section in self.additional_sections
            ],
        )

    @classmethod
    def from_domain_schema(cls, *, schema: ResumeContent) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                settings=ResumeSettingsSchema.from_domain_schema(schema=schema.settings),
                profile=ResumeProfileSchema.from_domain_schema(schema=schema.profile),
                summary=ResumeSummarySchema.from_domain_schema(schema=schema.summary),
                skills=[
                    ResumeSkillGroupSchema.from_domain_schema(schema=skill)
                    for skill in schema.skills
                ],
                experience=[
                    ResumeExperienceItemSchema.from_domain_schema(schema=experience)
                    for experience in schema.experience
                ],
                education=[
                    ResumeEducationItemSchema.from_domain_schema(schema=education)
                    for education in schema.education
                ],
                languages=[
                    ResumeLanguageItemSchema.from_domain_schema(schema=language)
                    for language in schema.languages
                ],
                certifications=[
                    ResumeCertificationItemSchema.from_domain_schema(schema=certification)
                    for certification in schema.certifications
                ],
                additional_sections=[
                    ResumeAdditionalSectionSchema.from_domain_schema(schema=section)
                    for section in schema.additional_sections
                ],
            ),
        )


class ResumeRequestSchema(CamelCaseSchema):
    title: Annotated[
        RequiredShortText,
        Field(
            title="Workspace title",
            description="Title used to identify this item.",
            examples=["Backend Engineer resume"],
        ),
    ]
    language: Annotated[
        LanguageEnum,
        Field(
            title="Resume language",
            description="Language; allowed values are listed in the referenced enumeration.",
            examples=["en"],
        ),
    ]
    content: Annotated[
        ResumeContentSchema,
        Field(
            title="Resume content",
            description=("Content; see the nested schema for its fields."),
        ),
    ]

    def to_create_schema(self, *, author_username: str) -> ResumeCreateParams:
        return ResumeCreateParams(
            title=self.title,
            language=self.language,
            content=self.content.to_domain_schema(),
            author_username=author_username,
        )

    def to_update_schema(self) -> ResumeUpdateParams:
        return ResumeUpdateParams(
            title=self.title,
            language=self.language,
            content=self.content.to_domain_schema(),
        )


class ResumeExportRequestSchema(ResumeRequestSchema):
    format: Annotated[
        ResumeExportFormatEnum,
        Field(
            title="Export format",
            description="Format; allowed values are listed in the referenced enumeration.",
            examples=["pdf"],
        ),
    ]
    theme: Annotated[
        ResumeThemeEnum,
        Field(
            title="Resume theme",
            description="Theme; allowed values are listed in the referenced enumeration.",
            examples=["simple"],
        ),
    ]

    def to_export_schema(self) -> ResumeExportParams:
        return ResumeExportParams(
            format=self.format,
            theme=self.theme,
            title=self.title,
            language=self.language,
            content=self.content.to_domain_schema(),
        )


class ResumeResponseSchema(CamelCaseSchema):
    id: Annotated[
        str,
        Field(
            title="Identifier",
            description="Opaque resource identifier; use the value returned by this API.",
            examples=["4e92d4de561f4bc7a3eed227868952db"],
        ),
    ]
    title: Annotated[
        str,
        Field(
            title="Workspace title",
            description="Title used to identify this item.",
            examples=["Backend Engineer resume"],
        ),
    ]
    language: Annotated[
        LanguageEnum,
        Field(
            title="Resume language",
            description="Language; allowed values are listed in the referenced enumeration.",
            examples=["en"],
        ),
    ]
    content: Annotated[
        ResumeContentSchema,
        Field(
            title="Resume content",
            description=("Content; see the nested schema for its fields."),
        ),
    ]
    created_at: Annotated[
        str,
        Field(
            title="Created at",
            description="Creation timestamp in ISO 8601 format.",
            examples=["2026-10-18T09:00:00Z"],
        ),
    ]
    updated_at: Annotated[
        str,
        Field(
            title="Updated at",
            description="Last modification timestamp in ISO 8601 format.",
            examples=["2026-10-18T10:30:00Z"],
        ),
    ]

    @classmethod
    def from_domain_schema(cls, *, schema: Resume) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                id=schema.id,
                title=schema.title,
                language=schema.language,
                content=ResumeContentSchema.from_domain_schema(schema=schema.content),
                created_at=schema.created_at.isoformat(),
                updated_at=schema.updated_at.isoformat(),
            ),
        )


class ResumesResponseSchema(CamelCaseSchema):
    total_count: Annotated[
        int,
        Field(
            title="Total count",
            description="Total number of matching records before pagination.",
            examples=[42],
        ),
    ]
    total_pages: Annotated[
        int,
        Field(
            title="Total pages",
            description=(
                "Number of pages for the requested pageSize; zero when there are no "
                "matching records."
            ),
            examples=[3],
        ),
    ]
    resumes: Annotated[
        list[ResumeResponseSchema],
        Field(title="Resumes", description="Resumes returned by this operation."),
    ]

    @classmethod
    def from_domain_schema(cls, *, schema: Resumes) -> Self:
        return cast(
            "Self",
            cls.model_construct(
                total_count=schema.total_count,
                total_pages=schema.total_pages,
                resumes=[
                    ResumeResponseSchema.from_domain_schema(schema=resume)
                    for resume in schema.values
                ],
            ),
        )
