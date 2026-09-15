import argparse
import json
import re
from collections.abc import Mapping, Sequence
from math import isfinite
from pathlib import Path
from statistics import median
from typing import cast

BASELINE_SAMPLE_COUNT = 5
_SOURCE_IDENTITY_PATTERN = re.compile(r"^workspace-sha256:[0-9a-f]{64}$")


def effective_execution_threshold_ms(
    *,
    sla_execution_ms: float,
    baseline_execution_ms: float,
) -> float:
    return min(
        sla_execution_ms,
        max(2 * baseline_execution_ms, baseline_execution_ms + 20.0),
    )


def build_baseline(*, source_sha: str, summary_paths: Sequence[Path]) -> dict[str, object]:
    validate_source_identity(source_sha=source_sha)
    if len(summary_paths) != BASELINE_SAMPLE_COUNT:
        msg = "baseline candidate requires exactly five summaries"
        raise ValueError(msg)
    summaries = tuple(load_summary(path=path) for path in summary_paths)
    run_ids = tuple(require_summary_text(summary=summary, key="runId") for summary in summaries)
    if len(set(run_ids)) != BASELINE_SAMPLE_COUNT:
        msg = "baseline samples require five distinct runId values"
        raise ValueError(msg)
    source_identities = {
        require_summary_text(summary=summary, key="sourceSha") for summary in summaries
    }
    if source_identities != {source_sha}:
        msg = "baseline sample sourceSha values must match the requested source SHA"
        raise ValueError(msg)
    query_samples: dict[str, list[float]] = {}
    expected_names: set[str] | None = None
    for summary in summaries:
        if summary["profile"] != "realistic":
            msg = "all baseline samples must use the realistic profile"
            raise ValueError(msg)
        findings = summary.get("findings")
        if not isinstance(findings, list) or findings:
            msg = "baseline samples must not contain blocking findings"
            raise ValueError(msg)
        sample_values = read_sample_values(results=cast("list[object]", summary["results"]))
        names = set(sample_values)
        if expected_names is None:
            expected_names = names
            query_samples = {name: [] for name in names}
        elif names != expected_names:
            msg = "baseline samples do not cover the same query set"
            raise ValueError(msg)
        for name, execution_ms in sample_values.items():
            query_samples[name].append(execution_ms)
    if not query_samples:
        msg = "baseline samples must contain queries"
        raise ValueError(msg)
    return {
        "profile": "realistic",
        "sourceSha": source_sha,
        "sampleCount": len(summaries),
        "queries": {
            name: median(execution_values)
            for name, execution_values in sorted(query_samples.items())
        },
    }


def read_sample_values(*, results: Sequence[object]) -> dict[str, float]:
    sample_values: dict[str, float] = {}
    for raw_result in results:
        if not isinstance(raw_result, Mapping):
            msg = "baseline result must be an object"
            raise TypeError(msg)
        name = raw_result.get("name")
        execution_ms = raw_result.get("executionMs")
        if not isinstance(name, str) or not isinstance(execution_ms, int | float):
            msg = "baseline result requires name and executionMs"
            raise TypeError(msg)
        if name in sample_values:
            msg = f"baseline summary contains duplicate query {name!r}"
            raise ValueError(msg)
        value = float(execution_ms)
        if not isfinite(value) or value < 0:
            msg = f"baseline timing for {name!r} must be finite non-negative"
            raise ValueError(msg)
        sample_values[name] = value
    return sample_values


def require_summary_text(*, summary: Mapping[str, object], key: str) -> str:
    value = summary.get(key)
    if not isinstance(value, str) or not value:
        msg = f"baseline summary requires non-empty {key}"
        raise ValueError(msg)
    return value


def validate_source_identity(*, source_sha: str) -> None:
    if _SOURCE_IDENTITY_PATTERN.fullmatch(source_sha) is None:
        msg = "sourceSha must be a workspace-sha256 identity"
        raise ValueError(msg)


def load_summary(*, path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"invalid query-plan summary object: {path}"
        raise TypeError(msg)
    if not isinstance(payload.get("results"), list):
        msg = f"invalid query-plan summary: {path}"
        raise TypeError(msg)
    return cast("dict[str, object]", payload)


def load_baseline(
    *,
    path: Path,
    expected_profile: str,
    expected_source_sha: str,
) -> dict[str, float]:
    validate_source_identity(source_sha=expected_source_sha)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        msg = "query-plan baseline must be an object"
        raise TypeError(msg)
    if payload.get("profile") != expected_profile:
        msg = "query-plan baseline profile mismatch"
        raise ValueError(msg)
    if payload.get("sourceSha") != expected_source_sha:
        msg = "query-plan baseline sourceSha mismatch"
        raise ValueError(msg)
    if payload.get("sampleCount") != BASELINE_SAMPLE_COUNT:
        msg = "query-plan baseline sampleCount must equal five"
        raise ValueError(msg)
    raw_queries = payload.get("queries")
    if not isinstance(raw_queries, Mapping) or not raw_queries:
        msg = "query-plan baseline queries must be a non-empty object"
        raise ValueError(msg)
    queries: dict[str, float] = {}
    for name, value in raw_queries.items():
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(value, int | float)
            or isinstance(value, bool)
            or not isfinite(float(value))
            or value < 0
        ):
            msg = "query-plan baseline queries must map names to non-negative numbers"
            raise ValueError(msg)
        queries[name] = float(value)
    return queries


def validate_baseline_query_coverage(
    *,
    baseline: Mapping[str, float],
    query_names: Sequence[str],
) -> None:
    baseline_names = set(baseline)
    current_names = set(query_names)
    findings: list[str] = []
    if missing := sorted(current_names - baseline_names):
        findings.append(f"missing baseline queries: {'; '.join(missing)}")
    if stale := sorted(baseline_names - current_names):
        findings.append(f"stale baseline queries: {'; '.join(stale)}")
    if findings:
        raise ValueError("; ".join(findings))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a query-plan baseline candidate from five clean summaries.",
    )
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, action="append", type=Path)
    args = parser.parse_args()
    baseline = build_baseline(source_sha=args.source_sha, summary_paths=args.summary)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
