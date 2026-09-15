from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.files.enums import FilePurpose
from core.knowledge.exceptions import KnowledgeConflictError, KnowledgeFileNotFoundError
from core.knowledge.files.enums import KnowledgeFileKind, KnowledgeFileProcessing
from core.knowledge.files.schemas import KnowledgeFile
from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.items.schemas import KnowledgeItemCreateParams
from infra.postgresql.models import FileModel, KnowledgeItemFileModel
from infra.postgresql.storages.files import FilesDatabaseStorage
from infra.postgresql.storages.knowledge.files import KnowledgeFilesDatabaseStorage
from infra.postgresql.storages.knowledge.items import KnowledgeItemsDatabaseStorage
from tests.test_cases import StorageTestCase

CURRENT_DATETIME = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
LOCK_TIMEOUT = "250ms"


class TestKnowledgeFilesDatabaseStorage(StorageTestCase):
    async def create_item(
        self,
        *,
        item_id: int,
        author_username: str = "owner",
        kind: KnowledgeItemKind = KnowledgeItemKind.PERSON,
    ) -> str:
        storage = KnowledgeItemsDatabaseStorage(session=self.db_session)
        item = await storage.create_item(
            params=KnowledgeItemCreateParams(
                kind=kind,
                author_username=author_username,
                display_name=f"Item {item_id}",
                description="",
            ),
        )
        return item.id

    def knowledge_file(
        self,
        *,
        file_id: int,
        item_id: str,
        kind: KnowledgeFileKind = KnowledgeFileKind.ATTACHMENT,
        processing: KnowledgeFileProcessing = KnowledgeFileProcessing.RAW,
        author_username: str = "owner",
    ) -> KnowledgeFile:
        relative_folder = (
            "person-photos" if kind == KnowledgeFileKind.PERSON_PHOTO else "attachments"
        )
        return KnowledgeFile(
            id=self.factory.core.hex_id(file_id),
            item_id=item_id,
            author_username=author_username,
            kind=kind,
            processing=processing,
            relative_path=f"{relative_folder}/{file_id}.bin",
            mime_type="application/octet-stream",
            size_bytes=10,
            name=f"File {file_id}",
            original_name=f"original-{file_id}.bin",
            original_sha256=f"{file_id:064x}",
            created_at=CURRENT_DATETIME,
            updated_at=CURRENT_DATETIME,
        )

    def storage(self) -> KnowledgeFilesDatabaseStorage:
        return KnowledgeFilesDatabaseStorage(
            session=self.db_session,
            namespace="knowledge-private",
        )

    async def test_create_list_get_and_rename_use_shared_file_metadata_with_author_scope(
        self,
    ) -> None:
        item_id = await self.create_item(item_id=1)
        file = self.knowledge_file(file_id=2, item_id=item_id)
        storage = self.storage()

        created = await storage.create_file(file=file)
        listed = await storage.list_item_files(item_id=item_id, author_username="owner")
        loaded = await storage.get_file(file_id=file.id, author_username="owner")
        renamed = await storage.update_file_name(
            file=file,
            name="Renamed",
            updated_at=CURRENT_DATETIME + timedelta(minutes=1),
        )
        metadata = await self.db_session.get(FileModel, file.id)

        assert created == file
        assert listed == [file]
        assert loaded == file
        assert renamed.name == "Renamed"
        assert metadata is not None
        assert metadata.purpose == FilePurpose.ATTACHMENT
        assert metadata.namespace == "knowledge-private"
        assert metadata.relative_path == file.relative_path
        assert metadata.name == "Renamed"
        assert metadata.orphaned_at is None
        with pytest.raises(KnowledgeFileNotFoundError):
            await storage.get_file(file_id=file.id, author_username="other-owner")

    async def test_processing_provenance_round_trips_on_knowledge_association(self) -> None:
        item_id = await self.create_item(item_id=1)
        file = self.knowledge_file(
            file_id=2,
            item_id=item_id,
            processing=KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE,
        )
        storage = self.storage()

        created = await storage.create_file(file=file)
        loaded = await storage.get_file(file_id=file.id, author_username="owner")
        link = await self.db_session.get(KnowledgeItemFileModel, file.id)

        assert created.processing == KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE
        assert loaded.processing == KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE
        assert link is not None
        assert link.processing == KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE

    async def test_file_usage_and_orphan_marker_follow_knowledge_association(self) -> None:
        item_id = await self.create_item(item_id=1)
        linked = self.knowledge_file(file_id=2, item_id=item_id)
        knowledge_storage = self.storage()
        files_storage = FilesDatabaseStorage(session=self.db_session)
        unlinked = self.factory.core.stored_file(
            file_id=3,
            namespace="media",
            original_sha256="b" * 64,
        )
        await knowledge_storage.create_file(file=linked)
        await files_storage.create_file(namespace="media", file=unlinked)

        assert (
            await files_storage.file_has_usages(
                namespace="knowledge-private",
                file_id=linked.id,
            )
            is True
        )
        assert await files_storage.file_has_usages(namespace="media", file_id=linked.id) is False
        assert (
            await files_storage.file_has_usages(
                namespace="knowledge-private",
                file_id=unlinked.id,
            )
            is False
        )
        assert await files_storage.file_has_usages(namespace="media", file_id=unlinked.id) is False

        orphaned_at = CURRENT_DATETIME + timedelta(days=1)
        await files_storage.set_files_orphaned_if_unused(
            namespace="knowledge-private",
            file_ids=frozenset({linked.id, unlinked.id}),
            orphaned_at=orphaned_at,
        )
        linked_metadata = await self.db_session.get(FileModel, linked.id)
        unlinked_metadata = await self.db_session.get(FileModel, unlinked.id)

        assert linked_metadata is not None
        assert linked_metadata.orphaned_at is None
        assert unlinked_metadata is not None
        assert unlinked_metadata.orphaned_at is None

    async def test_delete_file_unlinks_usage_without_removing_shared_metadata(self) -> None:
        item_id = await self.create_item(item_id=1)
        file = self.knowledge_file(file_id=2, item_id=item_id)
        storage = self.storage()
        await storage.create_file(file=file)

        await storage.delete_file(file=file)

        assert await self.db_session.get(FileModel, file.id) is not None
        assert await storage.list_item_files(item_id=item_id, author_username="owner") == []

    async def test_direct_metadata_delete_is_restricted_while_usage_exists(self) -> None:
        item_id = await self.create_item(item_id=1)
        file = self.knowledge_file(file_id=2, item_id=item_id)
        await self.storage().create_file(file=file)

        with pytest.raises(IntegrityError):
            await FilesDatabaseStorage(session=self.db_session).delete_file(
                namespace="knowledge-private",
                file_id=file.id,
            )

    async def test_unlink_then_relink_keeps_metadata_while_usage_remains(self) -> None:
        old_item_id = await self.create_item(item_id=1)
        new_item_id = await self.create_item(item_id=2)
        file = self.knowledge_file(file_id=3, item_id=old_item_id)
        knowledge_storage = self.storage()
        files_storage = FilesDatabaseStorage(session=self.db_session)
        await knowledge_storage.create_file(file=file)

        await files_storage.lock_files(
            namespace="knowledge-private",
            file_ids=frozenset({file.id}),
        )
        await knowledge_storage.delete_file(file=file)
        self.db_session.add(
            KnowledgeItemFileModel(
                file_id=file.id,
                item_id=new_item_id,
                author_username="owner",
                kind=KnowledgeFileKind.ATTACHMENT,
                processing=KnowledgeFileProcessing.RAW,
            ),
        )
        await self.db_session.flush()

        assert (
            await files_storage.file_has_usages(
                namespace="knowledge-private",
                file_id=file.id,
            )
            is True
        )
        assert await self.db_session.get(FileModel, file.id) is not None

    async def test_file_lock_serializes_concurrent_relink_and_preserves_new_usage(
        self,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        async with session_maker() as seed_session:
            item_storage = KnowledgeItemsDatabaseStorage(session=seed_session)
            old_item = await item_storage.create_item(
                params=KnowledgeItemCreateParams(
                    kind=KnowledgeItemKind.PERSON,
                    author_username="owner",
                    display_name="Old item",
                    description="",
                ),
            )
            new_item = await item_storage.create_item(
                params=KnowledgeItemCreateParams(
                    kind=KnowledgeItemKind.PERSON,
                    author_username="owner",
                    display_name="New item",
                    description="",
                ),
            )
            file = self.knowledge_file(file_id=3, item_id=old_item.id)
            await KnowledgeFilesDatabaseStorage(
                session=seed_session,
                namespace="knowledge-private",
            ).create_file(file=file)
            await seed_session.commit()

        async with session_maker() as relink_session, session_maker() as delete_session:
            relink_files = FilesDatabaseStorage(session=relink_session)
            relink_knowledge = KnowledgeFilesDatabaseStorage(
                session=relink_session,
                namespace="knowledge-private",
            )
            delete_files = FilesDatabaseStorage(session=delete_session)
            delete_knowledge = KnowledgeFilesDatabaseStorage(
                session=delete_session,
                namespace="knowledge-private",
            )
            stale_file = await delete_knowledge.get_file(
                file_id=file.id,
                author_username="owner",
            )

            await relink_files.lock_files(
                namespace="knowledge-private",
                file_ids=frozenset({file.id}),
            )
            await relink_knowledge.delete_file(file=file)
            relink_session.add(
                KnowledgeItemFileModel(
                    file_id=file.id,
                    item_id=new_item.id,
                    author_username="owner",
                    kind=KnowledgeFileKind.ATTACHMENT,
                    processing=KnowledgeFileProcessing.RAW,
                ),
            )
            await relink_session.flush()

            await delete_session.scalar(
                select(func.set_config("lock_timeout", LOCK_TIMEOUT, True)),
            )
            with pytest.raises(OperationalError):
                await delete_files.lock_files(
                    namespace="knowledge-private",
                    file_ids=frozenset({file.id}),
                )
            await delete_session.rollback()
            await relink_session.commit()

            await delete_files.lock_files(
                namespace="knowledge-private",
                file_ids=frozenset({file.id}),
            )
            with pytest.raises(KnowledgeFileNotFoundError):
                await delete_knowledge.delete_file(file=stale_file)
            await delete_session.rollback()

        async with session_maker() as verify_session:
            metadata = await verify_session.get(FileModel, file.id)
            verify_storage = KnowledgeFilesDatabaseStorage(
                session=verify_session,
                namespace="knowledge-private",
            )
            old_files = await verify_storage.list_item_files(
                item_id=old_item.id,
                author_username="owner",
            )
            new_files = await verify_storage.list_item_files(
                item_id=new_item.id,
                author_username="owner",
            )

        assert metadata is not None
        assert old_files == []
        assert [value.id for value in new_files] == [file.id]

    async def test_second_person_photo_conflicts(self) -> None:
        item_id = await self.create_item(item_id=1)
        storage = self.storage()
        await storage.create_file(
            file=self.knowledge_file(
                file_id=2,
                item_id=item_id,
                kind=KnowledgeFileKind.PERSON_PHOTO,
            ),
        )

        with pytest.raises(KnowledgeConflictError):
            await storage.create_file(
                file=self.knowledge_file(
                    file_id=3,
                    item_id=item_id,
                    kind=KnowledgeFileKind.PERSON_PHOTO,
                ),
            )
