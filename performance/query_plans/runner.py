import argparse
import asyncio
import json
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from sys import stdout
from time import perf_counter_ns
from typing import TYPE_CHECKING, cast

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from infra.config.settings import settings
from infra.postgresql.utils import migrate
from performance.query_plans.analysis import analyze_explain_result, analyze_scenario_indexes
from performance.query_plans.baseline import (
    effective_execution_threshold_ms,
    load_baseline,
    validate_baseline_query_coverage,
)
from performance.query_plans.database import validate_owned_database_name
from performance.query_plans.models import REALISTIC_PROFILE, CapturedQuery, QueryPlanProfile
from performance.query_plans.scenarios import SCENARIOS, StorageScenario
from performance.query_plans.seed import clear_seeded_tables, seed_profile

if TYPE_CHECKING:
    from typing import TextIO

MINIMUM_BLOCKING_CARDINALITY = 1_000
STATEMENT_TIMEOUT_MS = 60_000


class RuntimeQueryCapture:
    def __init__(self) -> None:
        self.queries: list[CapturedQuery] = []
        self.scenario: StorageScenario | None = None
        self.suspended = False

    def install(self, *, engine: AsyncEngine) -> None:
        event.listen(engine.sync_engine, "after_cursor_execute", self.capture_query)

    def capture_query(  # noqa: PLR0913
        self,
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: object,
    ) -> None:
        del connection, cursor, context, executemany
        if self.scenario is None or self.suspended:
            return
        statement_words = statement.lstrip().split(maxsplit=1)
        statement_type = statement_words[0].upper() if statement_words else ""
        if statement_type != "SELECT":
            msg = f"query-plan scenario captured non-SELECT statement: {statement_type or 'empty'}"
            raise RuntimeError(msg)
        ordinal = sum(query.scenario_name == self.scenario.name for query in self.queries) + 1
        self.queries.append(
            CapturedQuery(
                name=f"{self.scenario.name}__{ordinal:03d}",
                scenario_name=self.scenario.name,
                storage_class=self.scenario.storage_class,
                method_name=self.scenario.method_name,
                sql=statement,
                parameters=parameters,
                expectation=self.scenario.expectation,
            ),
        )

    @contextmanager
    def paused(self) -> Iterator[None]:
        self.suspended = True
        try:
            yield
        finally:
            self.suspended = False


def get_profile(*, name: str) -> QueryPlanProfile:
    if name == REALISTIC_PROFILE.name:
        return REALISTIC_PROFILE
    msg = f"Unknown query plan profile: {name}"
    raise ValueError(msg)


def emit_progress(*, stream: TextIO, message: str) -> None:
    stream.write(f"{message}\n")
    stream.flush()


async def run_query_plan_profile(  # noqa: PLR0913
    *,
    profile_name: str,
    report_dir: Path,
    baseline_path: Path | None,
    run_id: str,
    source_sha: str,
    progress: TextIO,
) -> int:
    profile = get_profile(name=profile_name)
    baseline = (
        load_baseline(
            path=baseline_path,
            expected_profile=profile.name,
            expected_source_sha=source_sha,
        )
        if baseline_path is not None
        else None
    )
    ensure_test_database()
    migrate(revision="heads")
    engine = create_async_engine(settings.database.url.get_secret_value(), poolclass=NullPool)
    capture = RuntimeQueryCapture()
    capture.install(engine=engine)
    await asyncio.to_thread(report_dir.mkdir, parents=True, exist_ok=True)

    async def workload() -> int:
        emit_progress(stream=progress, message="Query-plan phase: seed")
        async with engine.begin() as connection:
            await set_statement_timeout(connection=connection)
            await seed_profile(connection=connection, profile=profile)
        emit_progress(stream=progress, message="Query-plan phase: analyze seeded tables")
        async with engine.begin() as connection:
            await set_statement_timeout(connection=connection)
            await analyze_seeded_tables(connection=connection)
        emit_progress(stream=progress, message="Query-plan phase: capture scenarios")
        await capture_scenarios(
            engine=engine,
            capture=capture,
            progress=progress,
            session_factory=AsyncSession,
        )
        if baseline is not None:
            validate_baseline_query_coverage(
                baseline=baseline,
                query_names=tuple(query.name for query in capture.queries),
            )
        emit_progress(stream=progress, message="Query-plan phase: analyze captured statements")
        findings, results, scenario_checks = await analyze_captured_queries(
            engine=engine,
            capture=capture,
            profile=profile,
            baseline=baseline,
            progress=progress,
        )
        write_report(
            report_dir=report_dir,
            profile=profile,
            results=results,
            scenario_checks=scenario_checks,
            findings=findings,
            run_id=run_id,
            source_sha=source_sha,
        )
        emit_progress(stream=progress, message=f"Query-plan report: {report_dir / 'summary.md'}")
        emit_progress(stream=progress, message=f"Query-plan blocking findings: {len(findings)}")
        return 1 if findings else 0

    return await run_with_cleanup(
        engine=engine,
        progress=progress,
        workload=workload,
        cleanup=cleanup_runner,
    )


async def run_with_cleanup(
    *,
    engine: AsyncEngine,
    progress: TextIO,
    workload: Callable[[], Awaitable[int]],
    cleanup: Callable[..., Awaitable[None]],
) -> int:
    result: int | None = None
    primary_error: BaseException | None = None
    try:
        result = await workload()
    except BaseException as error:  # noqa: BLE001
        primary_error = error
    try:
        await cleanup(engine=engine, progress=progress)
    except BaseException as cleanup_error:
        if primary_error is not None:
            msg = "query-plan run and cleanup both failed"
            errors = (primary_error, cleanup_error)
            if all(isinstance(error, Exception) for error in errors):
                raise ExceptionGroup(msg, errors) from None  # type: ignore[arg-type]
            raise BaseExceptionGroup(msg, errors) from None
        raise
    if primary_error is not None:
        raise primary_error.with_traceback(primary_error.__traceback__)
    if result is None:
        msg = "query-plan run did not produce an exit status"
        raise RuntimeError(msg)
    return result


async def cleanup_runner(*, engine: AsyncEngine, progress: TextIO) -> None:
    emit_progress(stream=progress, message="Query-plan phase: cleanup")
    try:
        async with engine.begin() as connection:
            await set_statement_timeout(connection=connection)
            await clear_seeded_tables(connection=connection)
    finally:
        await engine.dispose()


def ensure_test_database() -> None:
    try:
        validate_owned_database_name(database_name=settings.database.name)
    except ValueError as error:
        msg = f"query plans require an owned isolated database, got {settings.database.name!r}"
        raise RuntimeError(msg) from error


async def analyze_seeded_tables(*, connection: AsyncConnection) -> None:
    await connection.execute(text("ANALYZE"))


async def set_statement_timeout(*, connection: AsyncConnection) -> None:
    await connection.execute(
        text("SELECT set_config('statement_timeout', :timeout, true)"),
        {"timeout": f"{STATEMENT_TIMEOUT_MS}ms"},
    )


async def capture_scenarios(
    *,
    engine: AsyncEngine,
    capture: RuntimeQueryCapture,
    progress: TextIO,
    session_factory: Callable[..., AsyncSession],
) -> None:
    for scenario in SCENARIOS:
        emit_progress(stream=progress, message=f"Query-plan scenario: {scenario.name}")
        async with session_factory(bind=engine, expire_on_commit=False) as session:
            try:
                await session.execute(text("SET TRANSACTION READ ONLY"))
                await session.execute(
                    text("SELECT set_config('statement_timeout', :timeout, true)"),
                    {"timeout": f"{STATEMENT_TIMEOUT_MS}ms"},
                )
                capture.scenario = scenario
                await asyncio.wait_for(scenario.run(session), timeout=STATEMENT_TIMEOUT_MS / 1_000)
            finally:
                capture.scenario = None
                await session.rollback()


async def analyze_captured_queries(
    *,
    engine: AsyncEngine,
    capture: RuntimeQueryCapture,
    profile: QueryPlanProfile,
    baseline: dict[str, float] | None,
    progress: TextIO,
) -> tuple[
    tuple[str, ...],
    tuple[dict[str, object], ...],
    tuple[dict[str, object], ...],
]:
    findings: list[str] = []
    results: list[dict[str, object]] = []
    scenario_indexes: dict[str, list[str]] = {scenario.name: [] for scenario in SCENARIOS}
    async with engine.begin() as connection:
        await set_statement_timeout(connection=connection)
        for query in capture.queries:
            emit_progress(stream=progress, message=f"Query-plan EXPLAIN: {query.name}")
            started_at = perf_counter_ns()
            with capture.paused():
                explain_result = await asyncio.wait_for(
                    connection.exec_driver_sql(
                        f"EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT JSON) {query.sql}",
                        query.parameters,
                    ),
                    timeout=STATEMENT_TIMEOUT_MS / 1_000,
                )
            row = explain_result.first()
            if row is None:
                msg = f"{query.name}: EXPLAIN returned no plan"
                raise RuntimeError(msg)
            explain_json = row[0]
            if isinstance(explain_json, str):
                explain_json = json.loads(explain_json)
            analysis = analyze_explain_result(
                name=query.name,
                explain_json=explain_json,
                expectation=query.expectation,
                relation_cardinalities=profile.relation_cardinalities,
                minimum_blocking_cardinality=MINIMUM_BLOCKING_CARDINALITY,
                execution_threshold_ms=(
                    effective_execution_threshold_ms(
                        sla_execution_ms=query.expectation.max_execution_ms,
                        baseline_execution_ms=baseline[query.name],
                    )
                    if baseline is not None
                    else query.expectation.max_execution_ms
                ),
            )
            findings.extend(f"{query.name}: {finding}" for finding in analysis.blocking_findings)
            scenario_indexes[query.scenario_name].extend(analysis.index_names)
            results.append(
                {
                    "name": query.name,
                    "scenario": query.scenario_name,
                    "storage": f"{query.storage_class}.{query.method_name}",
                    "explainElapsedMs": round((perf_counter_ns() - started_at) / 1_000_000, 2),
                    "executionMs": analysis.execution_time_ms,
                    "indexes": analysis.index_names,
                    "seqScans": analysis.seq_scan_relations,
                    "blockingFindings": analysis.blocking_findings,
                    "observations": analysis.observations,
                },
            )
    scenario_checks: list[dict[str, object]] = []
    for scenario in SCENARIOS:
        scenario_findings, scenario_observations = analyze_scenario_indexes(
            index_names=scenario_indexes[scenario.name],
            expectation=scenario.expectation,
            relation_cardinalities=profile.relation_cardinalities,
            minimum_blocking_cardinality=MINIMUM_BLOCKING_CARDINALITY,
        )
        findings.extend(f"{scenario.name}: {finding}" for finding in scenario_findings)
        scenario_checks.append(
            {
                "scenario": scenario.name,
                "expectedIndexes": tuple(
                    expected_index.name for expected_index in scenario.expectation.expected_indexes
                ),
                "observedIndexes": tuple(sorted(set(scenario_indexes[scenario.name]))),
                "blockingFindings": scenario_findings,
                "observations": scenario_observations,
            },
        )
    return tuple(findings), tuple(results), tuple(scenario_checks)


def write_report(  # noqa: PLR0913
    *,
    report_dir: Path,
    profile: QueryPlanProfile,
    results: tuple[dict[str, object], ...],
    scenario_checks: tuple[dict[str, object], ...],
    findings: tuple[str, ...],
    run_id: str,
    source_sha: str,
) -> None:
    summary = {
        "profile": profile.name,
        "runId": run_id,
        "sourceSha": source_sha,
        "relationCardinalities": profile.relation_cardinalities,
        "results": results,
        "scenarioChecks": scenario_checks,
        "findings": findings,
    }
    (report_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Knowledge and Resumes query-plan report",
        "",
        f"- Captured SELECT statements: {len(results)}",
        f"- Storage scenarios: {len(scenario_checks)}",
        f"- Blocking findings: {len(findings)}",
        "",
        "| Query | Storage | Execution (ms) | Indexes | Sequential scans |",
        "|---|---|---:|---|---|",
    ]
    lines.extend(
        "| {name} | {storage} | {execution} | {indexes} | {seq_scans} |".format(
            name=result["name"],
            storage=result["storage"],
            execution=result["executionMs"],
            indexes=", ".join(cast("tuple[str, ...]", result["indexes"])) or "—",
            seq_scans=", ".join(cast("tuple[str, ...]", result["seqScans"])) or "—",
        )
        for result in results
    )
    lines.extend(("", "## Findings", ""))
    lines.extend(f"- {finding}" for finding in findings)
    if not findings:
        lines.append("- No blocking plan findings.")
    (report_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Knowledge and Resumes PostgreSQL query-plan gate."
    )
    parser.add_argument("--profile", required=True, choices=(REALISTIC_PROFILE.name,))
    parser.add_argument("--report-dir", required=True, type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    raise SystemExit(
        asyncio.run(
            run_query_plan_profile(
                profile_name=args.profile,
                report_dir=args.report_dir,
                baseline_path=args.baseline,
                run_id=args.run_id,
                source_sha=args.source_sha,
                progress=stdout,
            ),
        ),
    )
