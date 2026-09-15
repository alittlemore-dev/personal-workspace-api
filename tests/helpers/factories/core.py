import hashlib
from datetime import UTC, date, datetime
from typing import Any

from core.auth.schemas import LoginParams, OwnerCredentials
from core.files.enums import FilePurpose
from core.files.schemas import FileRead, StoredFile
from core.files.types import Namespace
from core.i18n.enums import LanguageEnum
from core.resumes.enums import ResumeCurrentStatusEnum
from core.resumes.schemas import (
    Resume,
    ResumeAdditionalSection,
    ResumeAdditionalSectionItem,
    ResumeCertificationItem,
    ResumeContent,
    ResumeEducationItem,
    ResumeExperienceItem,
    ResumeLanguageItem,
    ResumeProfile,
    ResumeProjectItem,
    Resumes,
    ResumeSkillGroup,
    ResumeSummary,
)
from core.schemas import Secret
from core.types import SearchName

TEST_OWNER_USERNAME = "test-owner"
TEST_OWNER_PASSWORD = "test-owner-password"  # noqa: S105
TEST_ARGON2_HASH_PREFIX = "$argon2id$v=19$m=65536,t=3,p=4$"
TEST_ARGON2_HASH_SALT = "b73+a2Y9Ikr6PGBd1Wd6UA$"
TEST_ARGON2_HASH_DIGEST = "Prf9ZD9DpmMOUsaylDIMg1TFVmY/g1p8t2FJgFaaKFk"
TEST_OWNER_PASSWORD_HASH = (
    f"{TEST_ARGON2_HASH_PREFIX}{TEST_ARGON2_HASH_SALT}{TEST_ARGON2_HASH_DIGEST}"
)


class CoreFactoryHelper:
    @classmethod
    def owner_credentials(
        cls,
        username: str = TEST_OWNER_USERNAME,
        password_hash: str = TEST_OWNER_PASSWORD_HASH,
    ) -> OwnerCredentials:
        return OwnerCredentials(username=username, password_hash=Secret(password_hash))

    @classmethod
    def login_params(
        cls,
        username: str = TEST_OWNER_USERNAME,
        password: str = TEST_OWNER_PASSWORD,
    ) -> LoginParams:
        return LoginParams(username=username, password=Secret(password))

    @classmethod
    def hex_id(cls, value: int | str = 1) -> str:
        if isinstance(value, str):
            return value
        return f"{value % (1 << 128):032x}"

    @classmethod
    def hex_id_from_text(cls, value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()[:32]

    @classmethod
    def resume_content(
        cls,
        full_name: str = "Candidate Name",
        role: str = "Инженер",
        summary: str = "Короткое описание опыта.",
        skills: list[ResumeSkillGroup] | None = None,
        experience: list[ResumeExperienceItem] | None = None,
    ) -> ResumeContent:
        return ResumeContent(
            profile=ResumeProfile(
                full_name=full_name,
                role=role,
                location="",
                email="",
                phone="",
                website_url="",
                linkedin_url="",
                github_url="",
                telegram="",
            ),
            summary=ResumeSummary(text=summary),
            skills=skills
            if skills is not None
            else [ResumeSkillGroup(category="Backend", items=["Python", "PostgreSQL"])],
            experience=experience if experience is not None else [],
            education=[],
            languages=[],
            certifications=[],
            additional_sections=[],
        )

    @classmethod
    def resume_empty_content(cls, summary: str = "") -> ResumeContent:
        return ResumeContent(
            profile=ResumeProfile(
                full_name="",
                role="",
                location="",
                email="",
                phone="",
                website_url="",
                linkedin_url="",
                github_url="",
                telegram="",
            ),
            summary=ResumeSummary(text=summary),
            skills=[],
            experience=[],
            education=[],
            languages=[],
            certifications=[],
            additional_sections=[],
        )

    @classmethod
    def resume_full_content(
        cls,
        summary: str = "Builds reliable backend systems.",
        skill_items: list[str] | None = None,
    ) -> ResumeContent:
        return ResumeContent(
            profile=ResumeProfile(
                full_name="Dmitriy Ivanov",
                role="Backend engineer",
                location="Moscow",
                email="dmitriy@example.com",
                phone="+79990000000",
                website_url="https://example.com",
                linkedin_url="https://linkedin.com/in/dmitriy",
                github_url="https://github.com/dmitriy",
                telegram="@dmitriy",
            ),
            summary=ResumeSummary(text=summary),
            skills=[
                ResumeSkillGroup(
                    category="Languages",
                    items=skill_items if skill_items is not None else ["Python", "TypeScript"],
                ),
            ],
            experience=[
                ResumeExperienceItem(
                    company="Company",
                    position="Engineer",
                    location="Moscow",
                    start_date=date(2023, 1, 1),
                    end_date=None,
                    current_status=ResumeCurrentStatusEnum.CURRENT,
                    summary="Built platform services.",
                    highlights=["Reduced response time"],
                    technologies=["Python", "PostgreSQL"],
                    projects=[
                        ResumeProjectItem(
                            name="Portfolio",
                            role="Creator",
                            description="Site and knowledge base",
                            highlights=["Angular CSR"],
                            technologies=["Litestar", "Angular"],
                            url="https://example.com",
                        ),
                    ],
                ),
            ],
            education=[
                ResumeEducationItem(
                    institution="University",
                    degree="Bachelor",
                    field="Computer science",
                    location="Moscow",
                    start_date=date(2014, 9, 1),
                    end_date=date(2018, 6, 30),
                    description="Applied computer science",
                ),
            ],
            languages=[ResumeLanguageItem(name="English", proficiency="C1")],
            certifications=[
                ResumeCertificationItem(
                    name="Certificate",
                    issuer="Provider",
                    issued_on=date(2025, 1, 1),
                    expires_on=None,
                    credential_url="https://example.com/cert",
                ),
            ],
            additional_sections=[
                ResumeAdditionalSection(
                    title="Publications",
                    items=[
                        ResumeAdditionalSectionItem(
                            title="Article",
                            description="Technical write-up",
                            url="https://example.com/article",
                        ),
                    ],
                ),
            ],
        )

    @classmethod
    def resume(
        cls,
        resume_id: int | str = 1,
        title: str = "Backend resume",
        language: LanguageEnum = LanguageEnum.RU,
        content: ResumeContent | None = None,
        author_username: str = "test",
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> Resume:
        now = datetime.now(tz=UTC)
        return Resume(
            id=cls.hex_id(resume_id),
            title=title,
            language=language,
            content=content or cls.resume_content(),
            author_username=author_username,
            created_at=datetime.fromisoformat(created_at).replace(tzinfo=UTC)
            if created_at is not None
            else now,
            updated_at=datetime.fromisoformat(updated_at).replace(tzinfo=UTC)
            if updated_at is not None
            else now,
        )

    @classmethod
    def resumes(
        cls, values: list[Resume] | None = None, total_count: int = 0, total_pages: int = 0
    ) -> Resumes:
        return Resumes(values=values or [], total_count=total_count, total_pages=total_pages)

    @classmethod
    def stored_file(
        cls,
        file_id: int | str = 1,
        purpose: FilePurpose = FilePurpose.ATTACHMENT,
        namespace: Namespace = "media",
        relative_path: str = "attachments/file.png",
        mime_type: str = "image/png",
        size_bytes: int = 4,
        name: str = "Attachment",
        original_name: str = "original.png",
        original_sha256: str | None = None,
        orphaned_at: datetime | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> StoredFile:
        now = datetime(2026, 7, 3, 10, 0, tzinfo=UTC)
        return StoredFile(
            id=cls.hex_id(file_id) if isinstance(file_id, int) else file_id,
            purpose=purpose,
            namespace=namespace,
            relative_path=relative_path,
            mime_type=mime_type,
            size_bytes=size_bytes,
            name=name,
            original_name=original_name,
            original_sha256=original_sha256,
            orphaned_at=orphaned_at,
            created_at=created_at or now,
            updated_at=updated_at or now,
        )

    @classmethod
    def file_read(
        cls,
        file: StoredFile | None = None,
        access_url: str = "https://cdn.example.test/media/attachments/file.png",
        markdown_url: str = "https://cdn.example.test/media/attachments/file.png#fileId=00000000000000000000000000000001",
    ) -> FileRead:
        return FileRead(
            file=file or cls.stored_file(),
            access_url=access_url,
            markdown_url=markdown_url,
        )

    @classmethod
    def search_name(cls, value: Any) -> SearchName:
        return SearchName(value)
