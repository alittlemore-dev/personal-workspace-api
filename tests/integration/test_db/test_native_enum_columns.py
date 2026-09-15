from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.engine import Connection

from tests.test_cases import StorageTestCase

EXPECTED_ENUM_COLUMNS = {
    ("files__file_model", "purpose"): "file_purpose_enum",
    ("knowledge__knowledge_item_model", "kind"): "knowledge_item_kind_enum",
    ("knowledge__knowledge_item_file_model", "kind"): "knowledge_file_kind_enum",
    (
        "knowledge__knowledge_item_file_model",
        "processing",
    ): "knowledge_file_processing_enum",
    ("resumes__resume_model", "language"): "language_enum",
}


def inspect_enum_columns(connection: Connection) -> dict[tuple[str, str], tuple[bool, str]]:
    inspector = inspect(connection)
    result: dict[tuple[str, str], tuple[bool, str]] = {}
    for table_name, column_name in EXPECTED_ENUM_COLUMNS:
        column = next(
            value for value in inspector.get_columns(table_name) if value["name"] == column_name
        )
        column_type = column["type"]
        result[(table_name, column_name)] = (
            (column_type.native_enum, column_type.name or "")
            if isinstance(column_type, ENUM)
            else (False, "")
        )
    return result


class TestNativeEnumColumns(StorageTestCase):
    async def test_current_enum_columns_use_named_postgresql_enum_types(self) -> None:
        connection = await self.db_session.connection()

        actual = await connection.run_sync(inspect_enum_columns)

        assert actual == {
            key: (True, enum_name) for key, enum_name in EXPECTED_ENUM_COLUMNS.items()
        }
