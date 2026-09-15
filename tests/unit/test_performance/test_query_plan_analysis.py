from performance.query_plans.analysis import analyze_explain_result, analyze_scenario_indexes
from performance.query_plans.models import ExpectedIndex, PlanExpectation


class TestQueryPlanAnalysis:
    def test_large_relation_seq_scan_and_missing_index_are_blocking(self) -> None:
        analysis = analyze_explain_result(
            name="resumes_list__001",
            explain_json=[
                {
                    "Execution Time": 42.0,
                    "Plan": {
                        "Node Type": "Seq Scan",
                        "Relation Name": "resumes__resume_model",
                    },
                },
            ],
            expectation=PlanExpectation(
                max_execution_ms=100.0,
                expected_indexes=(
                    ExpectedIndex(
                        name="resumes_resume_author_updated_id_idx",
                        relation_name="resumes__resume_model",
                    ),
                ),
                forbidden_seq_scan_relations=("resumes__resume_model",),
            ),
            relation_cardinalities={"resumes__resume_model": 250},
            minimum_blocking_cardinality=100,
            execution_threshold_ms=100.0,
        )

        assert analysis.blocking_findings == ("Seq Scan on 250-row relation resumes__resume_model",)

    def test_small_relation_seq_scan_is_recorded_without_failing_the_gate(self) -> None:
        analysis = analyze_explain_result(
            name="knowledge_relationship_types__001",
            explain_json=[
                {
                    "Execution Time": 4.0,
                    "Plan": {
                        "Node Type": "Seq Scan",
                        "Relation Name": "knowledge__person_relationship_type_model",
                    },
                },
            ],
            expectation=PlanExpectation(
                max_execution_ms=100.0,
                expected_indexes=(),
                forbidden_seq_scan_relations=(),
            ),
            relation_cardinalities={"knowledge__person_relationship_type_model": 100},
            minimum_blocking_cardinality=1_000,
            execution_threshold_ms=100.0,
        )

        assert analysis.blocking_findings == ()
        assert analysis.observations == (
            "Seq Scan on 100-row relation knowledge__person_relationship_type_model",
        )

    def test_mapped_large_relation_seq_scan_is_blocking_without_manual_forbidden_list(
        self,
    ) -> None:
        analysis = analyze_explain_result(
            name="knowledge_files__001",
            explain_json=[
                {
                    "Execution Time": 1.0,
                    "Plan": {
                        "Node Type": "Seq Scan",
                        "Relation Name": "files__file_model",
                    },
                },
            ],
            expectation=PlanExpectation(
                max_execution_ms=100.0,
                expected_indexes=(),
                forbidden_seq_scan_relations=(),
            ),
            relation_cardinalities={"files__file_model": 5_000},
            minimum_blocking_cardinality=1_000,
            execution_threshold_ms=100.0,
        )

        assert analysis.blocking_findings == ("Seq Scan on 5000-row relation files__file_model",)

    def test_explicitly_allowed_large_relation_seq_scan_is_only_observed(self) -> None:
        analysis = analyze_explain_result(
            name="allowed__001",
            explain_json=[
                {
                    "Execution Time": 1.0,
                    "Plan": {"Node Type": "Seq Scan", "Relation Name": "large_relation"},
                },
            ],
            expectation=PlanExpectation(
                max_execution_ms=100.0,
                expected_indexes=(),
                forbidden_seq_scan_relations=(),
                allow_seq_scan_relations=("large_relation",),
            ),
            relation_cardinalities={"large_relation": 5_000},
            minimum_blocking_cardinality=1_000,
            execution_threshold_ms=100.0,
        )

        assert analysis.blocking_findings == ()
        assert analysis.observations == ("allowed Seq Scan on 5000-row relation large_relation",)

    def test_expected_index_may_appear_in_any_statement_captured_for_scenario(self) -> None:
        findings, observations = analyze_scenario_indexes(
            index_names=("knowledge_items_id_author_uniq",),
            expectation=PlanExpectation(
                max_execution_ms=100.0,
                expected_indexes=(
                    ExpectedIndex(
                        name="knowledge_items_id_author_uniq",
                        relation_name="knowledge__knowledge_item_model",
                    ),
                ),
                forbidden_seq_scan_relations=("knowledge__knowledge_item_model",),
            ),
            relation_cardinalities={"knowledge__knowledge_item_model": 5_000},
            minimum_blocking_cardinality=1_000,
        )

        assert findings == ()
        assert observations == ()

    def test_execution_above_effective_threshold_is_blocking(self) -> None:
        analysis = analyze_explain_result(
            name="people_page__001",
            explain_json=[
                {
                    "Execution Time": 120.25,
                    "Plan": {"Node Type": "Result"},
                },
            ],
            expectation=PlanExpectation(
                max_execution_ms=250.0,
                expected_indexes=(),
                forbidden_seq_scan_relations=(),
            ),
            relation_cardinalities={},
            minimum_blocking_cardinality=1_000,
            execution_threshold_ms=100.0,
        )

        assert analysis.blocking_findings == (
            "execution time 120.250 ms exceeds 100.000 ms threshold",
        )
