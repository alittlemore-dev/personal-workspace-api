from typing import Protocol, TypedDict, cast

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from infra.postgresql.utils import downgrade

EXPECTED_PROJECT_TABLES = {
    "files__file_model",
    "knowledge__date_details_model",
    "knowledge__date_person_model",
    "knowledge__knowledge_item_file_model",
    "knowledge__knowledge_item_model",
    "knowledge__knowledge_item_tag_model",
    "knowledge__knowledge_tag_model",
    "knowledge__person_details_model",
    "knowledge__person_relationship_model",
    "knowledge__person_relationship_type_model",
    "resumes__resume_model",
}
EXPECTED_ENUMS = {
    "file_purpose_enum",
    "knowledge_file_kind_enum",
    "knowledge_file_processing_enum",
    "knowledge_item_kind_enum",
    "language_enum",
}
FILE_ID = "10000000000040008000000000000001"
ITEM_ID = "10000000000040008000000000000002"
AUTHOR_USERNAME = "migration-owner"
file_purpose_enum = postgresql.ENUM(
    "ATTACHMENT",
    name="file_purpose_enum",
    create_type=False,
)
knowledge_item_kind_enum = postgresql.ENUM(
    "DATE",
    "PERSON",
    name="knowledge_item_kind_enum",
    create_type=False,
)
knowledge_file_kind_enum = postgresql.ENUM(
    "ATTACHMENT",
    "PERSON_PHOTO",
    name="knowledge_file_kind_enum",
    create_type=False,
)
knowledge_file_processing_enum = postgresql.ENUM(
    "RAW",
    "NORMALIZED_RASTER_IMAGE",
    name="knowledge_file_processing_enum",
    create_type=False,
)

files = sa.table(
    "files__file_model",
    sa.column("id", sa.String()),
    sa.column("purpose", file_purpose_enum),
    sa.column("namespace", sa.String()),
    sa.column("relative_path", sa.String()),
    sa.column("mime_type", sa.String()),
    sa.column("size_bytes", sa.Integer()),
    sa.column("name", sa.String()),
    sa.column("original_name", sa.String()),
    sa.column("original_sha256", sa.String()),
)
items = sa.table(
    "knowledge__knowledge_item_model",
    sa.column("id", sa.String()),
    sa.column("kind", knowledge_item_kind_enum),
    sa.column("author_username", sa.String()),
    sa.column("display_name", sa.String()),
    sa.column("description", sa.Text()),
)
item_files = sa.table(
    "knowledge__knowledge_item_file_model",
    sa.column("file_id", sa.String()),
    sa.column("item_id", sa.String()),
    sa.column("author_username", sa.String()),
    sa.column("kind", knowledge_file_kind_enum),
    sa.column("processing", knowledge_file_processing_enum),
)


class ReflectedEnum(TypedDict):
    name: str


class PostgreSQLInspector(Protocol):
    def get_enums(self) -> list[ReflectedEnum]: ...


def get_enum_names(connection: Connection) -> set[str]:
    inspector = cast("PostgreSQLInspector", sa.inspect(connection))
    return {enum["name"] for enum in inspector.get_enums()}


class TestMigration0001:
    async def test_upgrade_creates_current_file_and_knowledge_usage_schema(
        self,
        engine: AsyncEngine,
        migrated_to_0001: None,
    ) -> None:
        _ = migrated_to_0001
        async with engine.connect() as connection:
            tables = await connection.run_sync(
                lambda sync_connection: set(sa.inspect(sync_connection).get_table_names()),
            )
            file_columns = await connection.run_sync(
                lambda sync_connection: {
                    column["name"]
                    for column in sa.inspect(sync_connection).get_columns("files__file_model")
                },
            )
            link_columns = await connection.run_sync(
                lambda sync_connection: {
                    column["name"]
                    for column in sa.inspect(sync_connection).get_columns(
                        "knowledge__knowledge_item_file_model"
                    )
                },
            )
            link_foreign_keys = await connection.run_sync(
                lambda sync_connection: {
                    foreign_key["name"]: foreign_key["options"].get("ondelete")
                    for foreign_key in sa.inspect(sync_connection).get_foreign_keys(
                        "knowledge__knowledge_item_file_model"
                    )
                },
            )
            unique_link_indexes = await connection.run_sync(
                lambda sync_connection: {
                    index["name"]
                    for index in sa.inspect(sync_connection).get_indexes(
                        "knowledge__knowledge_item_file_model"
                    )
                    if index["unique"]
                },
            )
            enums = await connection.run_sync(get_enum_names)

        assert tables - {"alembic_version"} == EXPECTED_PROJECT_TABLES
        assert "knowledge__knowledge_file_model" not in tables
        assert file_columns == {
            "id",
            "purpose",
            "namespace",
            "relative_path",
            "mime_type",
            "size_bytes",
            "name",
            "original_name",
            "original_sha256",
            "orphaned_at",
            "created_at",
            "updated_at",
        }
        assert link_columns == {
            "file_id",
            "item_id",
            "author_username",
            "kind",
            "processing",
        }
        assert link_foreign_keys == {
            "knowledge_item_files_file_fk": "RESTRICT",
            "knowledge_item_files_item_author_fk": "RESTRICT",
        }
        assert "knowledge_item_files_one_person_photo_idx" in unique_link_indexes
        assert EXPECTED_ENUMS.issubset(enums)

    @pytest.mark.parametrize(
        "invalid_values",
        [
            pytest.param({"size_bytes": -1}, id="negative-size"),
            pytest.param({"name": "   "}, id="blank-name"),
            pytest.param({"original_name": "   "}, id="blank-original-name"),
            pytest.param({"original_sha256": "short"}, id="invalid-sha256-length"),
        ],
    )
    async def test_upgrade_enforces_shared_file_metadata_invariants(
        self,
        engine: AsyncEngine,
        migrated_to_0001: None,
        invalid_values: dict[str, int | str],
    ) -> None:
        _ = migrated_to_0001
        values: dict[str, int | str] = {
            "id": FILE_ID,
            "purpose": "ATTACHMENT",
            "namespace": "knowledge-private",
            "relative_path": "attachments/file.bin",
            "mime_type": "application/octet-stream",
            "size_bytes": 1,
            "name": "File",
            "original_name": "file.bin",
            "original_sha256": "a" * 64,
        }
        values.update(invalid_values)

        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(files.insert().values(**values))

    async def test_upgrade_restricts_deleting_linked_file_and_item(
        self,
        engine: AsyncEngine,
        migrated_to_0001: None,
    ) -> None:
        _ = migrated_to_0001
        async with engine.begin() as connection:
            await connection.execute(
                files.insert().values(
                    id=FILE_ID,
                    purpose="ATTACHMENT",
                    namespace="knowledge-private",
                    relative_path="attachments/file.bin",
                    mime_type="application/octet-stream",
                    size_bytes=1,
                    name="File",
                    original_name="file.bin",
                    original_sha256="a" * 64,
                ),
            )
            await connection.execute(
                items.insert().values(
                    id=ITEM_ID,
                    kind="PERSON",
                    author_username=AUTHOR_USERNAME,
                    display_name="Person",
                    description="",
                ),
            )
            await connection.execute(
                item_files.insert().values(
                    file_id=FILE_ID,
                    item_id=ITEM_ID,
                    author_username=AUTHOR_USERNAME,
                    kind="ATTACHMENT",
                    processing="RAW",
                ),
            )

            with pytest.raises(IntegrityError):
                async with connection.begin_nested():
                    await connection.execute(files.delete().where(files.c.id == FILE_ID))
            with pytest.raises(IntegrityError):
                async with connection.begin_nested():
                    await connection.execute(items.delete().where(items.c.id == ITEM_ID))

            assert (
                await connection.scalar(
                    sa.select(sa.func.count()).select_from(item_files),
                )
                == 1
            )

    async def test_downgrade_removes_project_schema(
        self,
        engine: AsyncEngine,
        migrated_to_0001: None,
    ) -> None:
        _ = migrated_to_0001

        downgrade(revision="base")

        async with engine.connect() as connection:
            tables = await connection.run_sync(
                lambda sync_connection: set(sa.inspect(sync_connection).get_table_names()),
            )
            enums = await connection.run_sync(get_enum_names)
        assert EXPECTED_PROJECT_TABLES.isdisjoint(tables)
        assert EXPECTED_ENUMS.isdisjoint(enums)
