import json
import os
import subprocess
import sys
from math import nan
from pathlib import Path

import pytest

from performance.query_plans.baseline import (
    BASELINE_SAMPLE_COUNT,
    build_baseline,
    effective_execution_threshold_ms,
    load_baseline,
    validate_baseline_query_coverage,
)


class TestQueryPlanBaseline:
    SOURCE_SHA = f"workspace-sha256:{'a' * 64}"

    def test_baseline_cli_import_does_not_require_application_settings(self) -> None:
        environment = os.environ.copy()
        environment.pop("FILES_ORPHAN_RETENTION_SECONDS", None)
        environment["PYTHONPATH"] = "src"

        result = subprocess.run(
            [sys.executable, "-m", "performance.query_plans.baseline", "--help"],
            cwd=Path(__file__).parents[3],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        assert "Build a query-plan baseline candidate" in result.stdout

    def test_build_baseline_uses_five_clean_samples_and_query_medians(self, tmp_path: Path) -> None:
        summary_paths = []
        execution_values = (10.0, 30.0, 20.0, 50.0, 40.0)
        for ordinal, execution_ms in enumerate(execution_values, start=1):
            path = tmp_path / f"summary-{ordinal}.json"
            path.write_text(
                (
                    '{"profile":"realistic","findings":[],"results":['
                    f'{{"name":"resumes_list__001","executionMs":{execution_ms}}}'
                    f'],"runId":"run-{ordinal}","sourceSha":"{self.SOURCE_SHA}"}}'
                ),
                encoding="utf-8",
            )
            summary_paths.append(path)

        baseline = build_baseline(source_sha=self.SOURCE_SHA, summary_paths=summary_paths)

        assert baseline == {
            "profile": "realistic",
            "sourceSha": self.SOURCE_SHA,
            "sampleCount": BASELINE_SAMPLE_COUNT,
            "queries": {"resumes_list__001": 30.0},
        }

    def test_build_baseline_rejects_a_sample_with_findings(self, tmp_path: Path) -> None:
        summary_paths = []
        for ordinal in range(BASELINE_SAMPLE_COUNT):
            summary_path = tmp_path / f"summary-{ordinal}.json"
            summary_path.write_text(
                (
                    '{"profile":"realistic","findings":["bad plan"],"results":[],'
                    f'"runId":"run-{ordinal}","sourceSha":"{self.SOURCE_SHA}"}}'
                ),
                encoding="utf-8",
            )
            summary_paths.append(summary_path)

        with pytest.raises(ValueError, match="blocking findings"):
            build_baseline(
                source_sha=self.SOURCE_SHA,
                summary_paths=summary_paths,
            )

    def test_build_baseline_requires_distinct_runs_with_same_truthful_source(
        self,
        tmp_path: Path,
    ) -> None:
        paths = []
        for ordinal in range(BASELINE_SAMPLE_COUNT):
            path = tmp_path / f"summary-{ordinal}.json"
            run_id = "duplicate" if ordinal < 2 else f"run-{ordinal}"
            source_sha = f"workspace-sha256:{'b' * 64}" if ordinal == 4 else self.SOURCE_SHA
            path.write_text(
                (
                    '{"profile":"realistic","findings":[],"results":['
                    '{"name":"query__001","executionMs":1.0}],'
                    f'"runId":"{run_id}","sourceSha":"{source_sha}"}}'
                ),
                encoding="utf-8",
            )
            paths.append(path)

        with pytest.raises(ValueError, match="distinct runId"):
            build_baseline(source_sha=self.SOURCE_SHA, summary_paths=paths)

        paths[1].write_text(
            paths[1].read_text(encoding="utf-8").replace("duplicate", "run-1"),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="sourceSha"):
            build_baseline(source_sha=self.SOURCE_SHA, summary_paths=paths)

    @pytest.mark.parametrize("execution_ms", [nan, float("inf"), -1.0])
    def test_build_baseline_rejects_non_finite_or_negative_timing(
        self,
        tmp_path: Path,
        execution_ms: float,
    ) -> None:
        paths = []
        for ordinal in range(BASELINE_SAMPLE_COUNT):
            path = tmp_path / f"summary-{ordinal}.json"
            path.write_text(
                json.dumps(
                    {
                        "profile": "realistic",
                        "findings": [],
                        "results": [{"name": "query__001", "executionMs": execution_ms}],
                        "runId": f"run-{ordinal}",
                        "sourceSha": self.SOURCE_SHA,
                    },
                ),
                encoding="utf-8",
            )
            paths.append(path)

        with pytest.raises(ValueError, match="finite non-negative"):
            build_baseline(source_sha=self.SOURCE_SHA, summary_paths=paths)

    def test_committed_baseline_requires_five_samples_and_exact_query_coverage(
        self,
        tmp_path: Path,
    ) -> None:
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(
            (
                f'{{"profile":"realistic","sourceSha":"{self.SOURCE_SHA}","sampleCount":5,'
                '"queries":{"resumes_list__001":1.0}}'
            ),
            encoding="utf-8",
        )

        baseline = load_baseline(
            path=baseline_path,
            expected_profile="realistic",
            expected_source_sha=self.SOURCE_SHA,
        )
        validate_baseline_query_coverage(
            baseline=baseline,
            query_names=("resumes_list__001",),
        )

        with pytest.raises(ValueError, match="missing baseline queries"):
            validate_baseline_query_coverage(
                baseline=baseline,
                query_names=("resumes_list__001", "people_page__001"),
            )

        with pytest.raises(ValueError, match="sourceSha mismatch"):
            load_baseline(
                path=baseline_path,
                expected_profile="realistic",
                expected_source_sha=f"workspace-sha256:{'b' * 64}",
            )

    def test_effective_threshold_keeps_sla_and_allows_fixed_runtime_noise(self) -> None:
        assert (
            effective_execution_threshold_ms(
                sla_execution_ms=250.0,
                baseline_execution_ms=10.0,
            )
            == 30.0
        )
        assert (
            effective_execution_threshold_ms(
                sla_execution_ms=15.0,
                baseline_execution_ms=10.0,
            )
            == 15.0
        )
