import pytest

from scripts.pytest_databases import validate_test_database_name


class TestValidateTestDatabaseName:
    @pytest.mark.parametrize(
        "database_name",
        [
            "personal_workspace_database_test",
            "personal_workspace_database_test_gw0",
            "personal_workspace_database_test_template_abcd1234",
        ],
    )
    def test_allows_test_database_names(self, database_name: str) -> None:
        validate_test_database_name(database_name)

    @pytest.mark.parametrize(
        "database_name",
        [
            "postgres",
            "personal_workspace_database",
            "production_testimony",
        ],
    )
    def test_rejects_non_test_database_names(self, database_name: str) -> None:
        with pytest.raises(ValueError, match="Refusing to manage non-test database"):
            validate_test_database_name(database_name)
