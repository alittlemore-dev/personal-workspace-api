from datetime import date
from typing import Annotated, Self, cast

from litestar.datastructures.upload_file import UploadFile
from pydantic import AfterValidator, ConfigDict, Field, model_validator

from core.i18n.enums import LanguageEnum
from core.resumes.enums import ResumeCurrentStatusEnum, ResumeExportFormatEnum, ResumeThemeEnum
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
    full_name: Annotated[RequiredShortText, Field(title="Full name")]
    photo_file_id: Annotated[
        str,
        Field(title="Photo file ID", max_length=32, pattern=r"^(?:[0-9a-f]{32})?$"),
    ]
    role: Annotated[RequiredShortText, Field(title="Role")]
    location: Annotated[ResumeOptionalShortText, Field(title="Location")]
    email: Annotated[BlankableEmailString, Field(title="Email")]
    phone: Annotated[
        str,
        Field(title="Phone", max_length=64),
        AfterValidator(validate_resume_phone),
    ]
    website_url: Annotated[BlankableHttpUrlString, Field(title="Website URL")]
    linkedin_url: Annotated[BlankableHttpUrlString, Field(title="LinkedIn URL")]
    github_url: Annotated[BlankableHttpUrlString, Field(title="GitHub URL")]
    telegram: Annotated[ResumeOptionalShortText, Field(title="Telegram")]

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

    file: Annotated[UploadFile, Field(title="Resume photo")]


class ResumeSummarySchema(CamelCaseSchema):
    text: Annotated[ResumeLongText, Field(title="Summary", max_length=ResumeLimits.summary)]

    def to_domain_schema(self) -> ResumeSummary:
        return ResumeSummary(text=self.text)

    @classmethod
    def from_domain_schema(cls, *, schema: ResumeSummary) -> Self:
        return cast("Self", cls.model_construct(text=schema.text))


class ResumeSkillGroupSchema(CamelCaseSchema):
    category: Annotated[RequiredShortText, Field(title="Skill category")]
    items: Annotated[
        list[RequiredShortText],
        Field(title="Skill items", min_length=1, max_length=ResumeLimits.skills_per_group),
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
    name: Annotated[RequiredShortText, Field(title="Project name")]
    role: Annotated[RequiredShortText, Field(title="Project role")]
    team_size: Annotated[ResumeOptionalShortText, Field(title="Team size")]
    scale: Annotated[ResumeOptionalShortText, Field(title="Project scale")]
    description: Annotated[
        ResumeLongText,
        Field(title="Project description", max_length=ResumeLimits.project_description),
    ]
    highlights: Annotated[
        list[Annotated[RequiredResumeLongText, Field(max_length=ResumeLimits.highlight)]],
        Field(title="Highlights", max_length=ResumeLimits.project_highlights),
    ]
    technologies: Annotated[
        list[RequiredShortText],
        Field(title="Technologies", max_length=ResumeLimits.project_technologies),
    ]
    url: Annotated[BlankableHttpUrlString, Field(title="Project URL")]

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
    company: Annotated[RequiredShortText, Field(title="Company")]
    company_website_url: Annotated[BlankableHttpUrlString, Field(title="Company website URL")]
    position: Annotated[RequiredShortText, Field(title="Position")]
    location: Annotated[ResumeOptionalShortText, Field(title="Location")]
    start_date: Annotated[date, Field(title="Start date")]
    end_date: Annotated[date | None, Field(title="End date")]
    current_status: Annotated[ResumeCurrentStatusEnum, Field(title="Current status")]
    summary: Annotated[
        ResumeLongText,
        Field(title="Experience summary", max_length=ResumeLimits.experience_summary),
    ]
    highlights: Annotated[
        list[Annotated[RequiredResumeLongText, Field(max_length=ResumeLimits.highlight)]],
        Field(title="Highlights", max_length=ResumeLimits.experience_highlights),
    ]
    technologies: Annotated[
        list[RequiredShortText],
        Field(title="Technologies", max_length=ResumeLimits.experience_technologies),
    ]
    projects: Annotated[
        list[ResumeProjectItemSchema],
        Field(title="Experience projects", max_length=ResumeLimits.projects_per_experience),
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
                start_date=cast("date", schema.start_date),
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
    institution: Annotated[RequiredShortText, Field(title="Institution")]
    degree: Annotated[RequiredShortText, Field(title="Degree")]
    field: Annotated[RequiredShortText, Field(title="Field")]
    location: Annotated[RequiredShortText, Field(title="Location")]
    start_date: Annotated[date, Field(title="Start date")]
    end_date: Annotated[date | None, Field(title="End date")]
    description: Annotated[
        ResumeLongText,
        Field(title="Description", max_length=ResumeLimits.education_description),
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
                start_date=cast("date", schema.start_date),
                end_date=schema.end_date,
                description=schema.description,
            ),
        )


class ResumeLanguageItemSchema(CamelCaseSchema):
    name: Annotated[RequiredShortText, Field(title="Language")]
    proficiency: Annotated[RequiredShortText, Field(title="Proficiency")]

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
    name: Annotated[RequiredShortText, Field(title="Certification")]
    issuer: Annotated[ResumeOptionalShortText, Field(title="Issuer")]
    issued_on: Annotated[date | None, Field(title="Issued on")]
    expires_on: Annotated[date | None, Field(title="Expires on")]
    credential_url: Annotated[BlankableHttpUrlString, Field(title="Credential URL")]

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
    title: Annotated[RequiredShortText, Field(title="Title")]
    description: Annotated[
        ResumeLongText,
        Field(title="Description", max_length=ResumeLimits.additional_description),
    ]
    url: Annotated[BlankableHttpUrlString, Field(title="URL")]

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
    title: Annotated[RequiredShortText, Field(title="Section title")]
    items: Annotated[
        list[ResumeAdditionalSectionItemSchema],
        Field(
            title="Section items",
            min_length=1,
            max_length=ResumeLimits.additional_items_per_section,
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


class ResumeContentSchema(CamelCaseSchema):
    profile: Annotated[ResumeProfileSchema, Field(title="Profile")]
    summary: Annotated[ResumeSummarySchema, Field(title="Summary")]
    skills: Annotated[
        list[ResumeSkillGroupSchema],
        Field(title="Skills", max_length=ResumeLimits.skill_groups),
    ]
    experience: Annotated[
        list[ResumeExperienceItemSchema],
        Field(title="Experience", max_length=ResumeLimits.experience),
    ]
    education: Annotated[
        list[ResumeEducationItemSchema],
        Field(title="Education", max_length=ResumeLimits.education),
    ]
    languages: Annotated[
        list[ResumeLanguageItemSchema],
        Field(title="Languages", max_length=ResumeLimits.languages),
    ]
    certifications: Annotated[
        list[ResumeCertificationItemSchema],
        Field(title="Certifications", max_length=ResumeLimits.certifications),
    ]
    additional_sections: Annotated[
        list[ResumeAdditionalSectionSchema],
        Field(title="Additional sections", max_length=ResumeLimits.additional_sections),
    ]

    validate_totals = model_validator(mode="after")(validate_resume_totals)

    def to_domain_schema(self) -> ResumeContent:
        return ResumeContent(
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
    title: Annotated[RequiredShortText, Field(title="Workspace title")]
    language: Annotated[LanguageEnum, Field(title="Resume language")]
    content: Annotated[ResumeContentSchema, Field(title="Resume content")]

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
    format: Annotated[ResumeExportFormatEnum, Field(title="Export format")]
    theme: Annotated[ResumeThemeEnum, Field(title="Resume theme")]

    def to_export_schema(self) -> ResumeExportParams:
        return ResumeExportParams(
            format=self.format,
            theme=self.theme,
            title=self.title,
            language=self.language,
            content=self.content.to_domain_schema(),
        )


class ResumeResponseSchema(CamelCaseSchema):
    id: Annotated[str, Field(title="Identifier")]
    title: Annotated[str, Field(title="Workspace title")]
    language: Annotated[LanguageEnum, Field(title="Resume language")]
    content: Annotated[ResumeContentSchema, Field(title="Resume content")]
    created_at: Annotated[str, Field(title="Created at")]
    updated_at: Annotated[str, Field(title="Updated at")]

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
    total_count: Annotated[int, Field(title="Total count")]
    total_pages: Annotated[int, Field(title="Total pages")]
    resumes: Annotated[list[ResumeResponseSchema], Field(title="Resumes")]

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
