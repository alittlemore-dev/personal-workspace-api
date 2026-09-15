from performance.query_plans.identifiers import seeded_identifier
from performance.query_plans.scenarios import (
    SCENARIOS,
    SEED_DATE_ID,
    SEED_PERSON_ID,
    SEED_TAG_ID,
)


class TestQueryPlanScenarios:
    def test_scenarios_cover_only_current_knowledge_and_resumes_storage_reads(self) -> None:
        assert {(scenario.storage_class, scenario.method_name) for scenario in SCENARIOS} == {
            ("ResumesDatabaseStorage", "list_resumes"),
            ("KnowledgeItemsDatabaseStorage", "get_item"),
            ("KnowledgeItemsDatabaseStorage", "list_tags"),
            ("KnowledgeDatesDatabaseStorage", "list_date_page"),
            ("KnowledgeDatesDatabaseStorage", "list_date_ids_for_person"),
            ("PeopleDatabaseStorage", "list_person_page"),
            ("PeopleDatabaseStorage", "list_relationships"),
            ("KnowledgeFilesDatabaseStorage", "list_files_for_items"),
        }

    def test_each_scenario_declares_indexes_or_an_explicit_small_relation_allowance(self) -> None:
        for scenario in SCENARIOS:
            expectation = scenario.expectation
            assert expectation.expected_indexes or expectation.allow_seq_scan_relations

    def test_scenario_ids_match_the_deterministic_seed_identifiers(self) -> None:
        assert seeded_identifier(prefix="person", value=1) == SEED_PERSON_ID
        assert seeded_identifier(prefix="date", value=1) == SEED_DATE_ID
        assert seeded_identifier(prefix="tag", value=1) == SEED_TAG_ID
