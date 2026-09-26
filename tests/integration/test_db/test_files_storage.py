from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Literal

import pytest
from sqlalchemy.exc import IntegrityError

from core.exceptions import EntryNotFoundError
from core.files.enums import FilePurpose
from core.i18n.enums import LanguageEnum
from core.resumes.schemas import ResumeCreateParams
from infra.postgresql.models import FileModel
from infra.postgresql.storages.files import FilesDatabaseStorage
from infra.postgresql.storages.resumes import ResumesDatabaseStorage
from tests.test_cases import StorageTestCase

CURRENT_DATETIME = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


class TestFilesDatabaseStorage(StorageTestCase):
    async def test_resume_photo_reference_keeps_private_file_attached(self) -> None:
        files = FilesDatabaseStorage(session=self.db_session)
        resumes = ResumesDatabaseStorage(session=self.db_session)
        photo = self.factory.core.stored_file(
            file_id=7,
            namespace="resume-private",
            relative_path="photos/photo.jpg",
            mime_type="image/jpeg",
            orphaned_at=CURRENT_DATETIME,
        )
        await files.create_file(namespace="resume-private", file=photo)
        content = self.factory.core.resume_empty_content()
        content = replace(content, profile=replace(content.profile, photo_file_id=photo.id))
        resume = await resumes.create_resume(
            params=ResumeCreateParams(
                title="Resume",
                language=LanguageEnum.EN,
                content=content,
                author_username="admin",
            ),
        )

        assert await files.file_has_usages(namespace="resume-private", file_id=photo.id)
        await files.set_files_attached(namespace="resume-private", file_ids=frozenset({photo.id}))
        await files.set_files_orphaned_if_unused(
            namespace="resume-private",
            file_ids=frozenset({photo.id}),
            orphaned_at=CURRENT_DATETIME,
        )
        assert (
            await files.get_file(namespace="resume-private", file_id=photo.id)
        ).orphaned_at is None

        await resumes.delete_resume(resume_id=resume.id, author_username="admin")
        assert not await files.file_has_usages(namespace="resume-private", file_id=photo.id)

    async def test_crud_is_isolated_by_namespace(self) -> None:
        storage = FilesDatabaseStorage(session=self.db_session)
        media_file = self.factory.core.stored_file(
            file_id=1,
            namespace="media",
            relative_path="attachments/shared-name.bin",
        )
        private_file = self.factory.core.stored_file(
            file_id=2,
            namespace="knowledge-private",
            relative_path="attachments/shared-name.bin",
        )
        await storage.create_file(namespace="media", file=media_file)
        await storage.create_file(namespace="knowledge-private", file=private_file)

        assert (
            await storage.list_files(namespace="media", purpose=FilePurpose.ATTACHMENT)
        ).values == [media_file]
        assert (
            await storage.list_files(
                namespace="knowledge-private",
                purpose=FilePurpose.ATTACHMENT,
            )
        ).values == [private_file]
        assert await storage.get_file(namespace="media", file_id=media_file.id) == media_file
        assert (
            await storage.get_file(namespace="knowledge-private", file_id=private_file.id)
            == private_file
        )
        with pytest.raises(EntryNotFoundError):
            await storage.get_file(namespace="media", file_id=private_file.id)
        with pytest.raises(EntryNotFoundError):
            await storage.get_file(namespace="knowledge-private", file_id=media_file.id)

        with pytest.raises(EntryNotFoundError):
            await storage.update_file_name(
                namespace="media",
                file_id=private_file.id,
                name="Guessed private file",
                updated_at=CURRENT_DATETIME + timedelta(minutes=1),
            )
        await storage.delete_file(namespace="media", file_id=private_file.id)
        await storage.delete_file(namespace="knowledge-private", file_id=media_file.id)

        assert (
            await storage.get_file(namespace="knowledge-private", file_id=private_file.id)
        ).name == private_file.name
        assert await storage.get_file(namespace="media", file_id=media_file.id) == media_file

    async def test_orphan_transitions_are_isolated_by_namespace(self) -> None:
        storage = FilesDatabaseStorage(session=self.db_session)
        orphaned_at = CURRENT_DATETIME - timedelta(days=2)
        media_file = self.factory.core.stored_file(
            file_id=1,
            namespace="media",
            orphaned_at=orphaned_at,
        )
        private_file = self.factory.core.stored_file(
            file_id=2,
            namespace="knowledge-private",
            relative_path="attachments/private.bin",
            orphaned_at=orphaned_at,
        )
        await storage.create_file(namespace="media", file=media_file)
        await storage.create_file(namespace="knowledge-private", file=private_file)

        await storage.set_files_attached(
            namespace="media",
            file_ids=frozenset({private_file.id}),
        )
        await storage.set_files_orphaned_if_unused(
            namespace="knowledge-private",
            file_ids=frozenset({media_file.id}),
            orphaned_at=CURRENT_DATETIME,
        )
        with pytest.raises(EntryNotFoundError):
            await storage.refresh_file_orphaned_at(
                namespace="media",
                file_id=private_file.id,
                orphaned_at=CURRENT_DATETIME,
            )

        assert (
            await storage.get_file(namespace="knowledge-private", file_id=private_file.id)
        ).orphaned_at == orphaned_at
        assert (
            await storage.get_file(namespace="media", file_id=media_file.id)
        ).orphaned_at == orphaned_at

    @pytest.mark.parametrize(
        "invalid_field",
        [
            "size_bytes",
            "name",
            "original_name",
            "original_sha256",
        ],
    )
    async def test_database_rejects_invalid_file_metadata(
        self,
        invalid_field: Literal["size_bytes", "name", "original_name", "original_sha256"],
    ) -> None:
        stored_file = self.factory.core.stored_file(file_id=1)
        match invalid_field:
            case "size_bytes":
                stored_file = replace(stored_file, size_bytes=-1)
            case "name":
                stored_file = replace(stored_file, name="   ")
            case "original_name":
                stored_file = replace(stored_file, original_name="   ")
            case "original_sha256":
                stored_file = replace(stored_file, original_sha256="short")
        self.db_session.add(FileModel.from_domain_schema(stored_file))

        with pytest.raises(IntegrityError):
            await self.db_session.flush()
