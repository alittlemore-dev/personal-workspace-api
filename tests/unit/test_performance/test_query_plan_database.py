import pytest

from performance.query_plans.database import (
    build_run_database_name,
    validate_owned_database_name,
)


class TestQueryPlanDatabase:
    def test_run_database_names_are_isolated_and_safe_for_postgresql(self) -> None:
        first = build_run_database_name(
            base_name="personal_workspace_database_test", run_id="run-one"
        )
        second = build_run_database_name(
            base_name="personal_workspace_database_test", run_id="run-two"
        )

        assert first != second
        assert first.startswith("personal_workspace_database_test_query_plans_")
        assert len(first.encode()) <= 63
        validate_owned_database_name(database_name=first)

    @pytest.mark.parametrize(
        "database_name",
        [
            "personal_workspace_database_test",
            "production",
            "personal_workspace_database_test_query_plans_unsafe-name",
        ],
    )
    def test_cleanup_rejects_non_owned_database_names(self, database_name: str) -> None:
        with pytest.raises(ValueError, match="owned query-plan database"):
            validate_owned_database_name(database_name=database_name)
