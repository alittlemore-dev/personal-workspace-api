from collections.abc import Iterator, Mapping, Sequence
from typing import cast

from performance.query_plans.models import PlanAnalysis, PlanExpectation


def analyze_explain_result(  # noqa: PLR0913
    *,
    name: str,
    explain_json: Sequence[object],
    expectation: PlanExpectation,
    relation_cardinalities: Mapping[str, int],
    minimum_blocking_cardinality: int,
    execution_threshold_ms: float,
) -> PlanAnalysis:
    entry = cast("Mapping[str, object]", explain_json[0])
    plan = cast("Mapping[str, object]", entry["Plan"])
    nodes = tuple(iter_plan_nodes(plan=plan))
    index_names = tuple(
        index_name for node in nodes if isinstance((index_name := node.get("Index Name")), str)
    )
    seq_scan_relations = tuple(
        relation_name
        for node in nodes
        if node.get("Node Type") == "Seq Scan"
        and isinstance((relation_name := node.get("Relation Name")), str)
    )
    blocking_findings: list[str] = []
    observations: list[str] = []
    execution_time_ms = float(cast("int | float", entry.get("Execution Time", 0.0)))
    if execution_time_ms > execution_threshold_ms:
        blocking_findings.append(
            f"execution time {execution_time_ms:.3f} ms exceeds "
            f"{execution_threshold_ms:.3f} ms threshold",
        )
    for relation_name in seq_scan_relations:
        if relation_name in expectation.allow_seq_scan_relations:
            continue
        cardinality = relation_cardinalities.get(relation_name, 0)
        message = f"Seq Scan on {cardinality}-row relation {relation_name}"
        if cardinality >= minimum_blocking_cardinality:
            blocking_findings.append(message)
        elif relation_name in expectation.forbidden_seq_scan_relations:
            observations.append(message)
    for relation_name in seq_scan_relations:
        if relation_name in expectation.allow_seq_scan_relations:
            observations.append(
                f"allowed Seq Scan on {relation_cardinalities.get(relation_name, 0)}-row "
                f"relation {relation_name}"
            )
        elif (
            relation_name not in expectation.forbidden_seq_scan_relations
            and relation_cardinalities.get(relation_name, 0) < minimum_blocking_cardinality
        ):
            observations.append(
                f"Seq Scan on {relation_cardinalities.get(relation_name, 0)}-row "
                f"relation {relation_name}"
            )
    return PlanAnalysis(
        name=name,
        execution_time_ms=execution_time_ms,
        index_names=index_names,
        seq_scan_relations=seq_scan_relations,
        blocking_findings=tuple(blocking_findings),
        observations=tuple(observations),
    )


def analyze_scenario_indexes(
    *,
    index_names: Sequence[str],
    expectation: PlanExpectation,
    relation_cardinalities: Mapping[str, int],
    minimum_blocking_cardinality: int,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    findings: list[str] = []
    observations: list[str] = []
    for expected_index in expectation.expected_indexes:
        if expected_index.name in index_names:
            continue
        append_relation_finding(
            findings=findings,
            observations=observations,
            message=(
                f"missing expected index {expected_index.name} on "
                f"{relation_cardinalities.get(expected_index.relation_name, 0)}-row relation "
                f"{expected_index.relation_name}"
            ),
            relation_cardinality=relation_cardinalities.get(expected_index.relation_name, 0),
            minimum_blocking_cardinality=minimum_blocking_cardinality,
        )
    return tuple(findings), tuple(observations)


def append_relation_finding(
    *,
    findings: list[str],
    observations: list[str],
    message: str,
    relation_cardinality: int,
    minimum_blocking_cardinality: int,
) -> None:
    if relation_cardinality >= minimum_blocking_cardinality:
        findings.append(message)
    else:
        observations.append(message)


def iter_plan_nodes(*, plan: Mapping[str, object]) -> Iterator[Mapping[str, object]]:
    yield plan
    children = plan.get("Plans", ())
    if not isinstance(children, Sequence):
        return
    for child in children:
        if isinstance(child, Mapping):
            yield from iter_plan_nodes(plan=cast("Mapping[str, object]", child))
