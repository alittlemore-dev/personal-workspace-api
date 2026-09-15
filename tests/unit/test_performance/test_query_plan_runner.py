import asyncio
from collections.abc import Awaitable, Callable
from io import StringIO
from unittest.mock import ANY, AsyncMock, Mock

import pytest

from performance.query_plans.runner import (
    RuntimeQueryCapture,
    capture_scenarios,
    cleanup_runner,
    emit_progress,
    run_with_cleanup,
)
from performance.query_plans.scenarios import SCENARIOS


class FlushTrackingStream(StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.flush_count = 0

    def flush(self) -> None:
        self.flush_count += 1
        super().flush()


class TestQueryPlanRunner:
    def test_progress_is_flushed_for_ci_visibility(self) -> None:
        stream = FlushTrackingStream()

        emit_progress(stream=stream, message="Query-plan phase: seed")

        assert stream.getvalue() == "Query-plan phase: seed\n"
        assert stream.flush_count == 1

    def test_runtime_capture_rejects_non_select_statements(self) -> None:
        capture = RuntimeQueryCapture()
        capture.scenario = SCENARIOS[0]

        with pytest.raises(RuntimeError, match="non-SELECT"):
            capture.capture_query(
                connection=None,  # type: ignore[arg-type]
                cursor=object(),
                statement="UPDATE resumes__resume_model SET title = 'unsafe'",
                parameters={},
                context=object(),
                executemany=False,
            )

    async def test_scenarios_enter_read_only_transaction_before_capture(self) -> None:
        session = AsyncMock()
        session.execute.side_effect = [Mock(), RuntimeError("stop after transaction setup")]
        session.rollback = AsyncMock()
        session_context = AsyncMock()
        session_context.__aenter__.return_value = session
        session_context.__aexit__.return_value = False
        engine = Mock()

        with pytest.raises(RuntimeError, match="stop after transaction setup"):
            await capture_scenarios(
                engine=engine,
                capture=RuntimeQueryCapture(),
                progress=StringIO(),
                session_factory=lambda **_: session_context,
            )

        statements = [str(call.args[0]) for call in session.execute.await_args_list]
        assert statements == [
            "SET TRANSACTION READ ONLY",
            "SELECT set_config('statement_timeout', :timeout, true)",
        ]

    async def test_cleanup_disposes_engine_when_database_cleanup_fails(self) -> None:
        engine = Mock()
        engine.dispose = AsyncMock()
        connection_context = AsyncMock()
        connection = AsyncMock()
        connection.execute.side_effect = RuntimeError("cleanup failed")
        connection_context.__aenter__.return_value = connection
        connection_context.__aexit__.return_value = False
        engine.begin.return_value = connection_context

        with pytest.raises(RuntimeError, match="cleanup failed"):
            await cleanup_runner(engine=engine, progress=StringIO())

        engine.dispose.assert_awaited_once()

    async def test_cancellation_still_runs_cleanup_and_is_preserved(self) -> None:
        engine = Mock()
        workload = AsyncMock(side_effect=asyncio.CancelledError)
        cleanup = AsyncMock()

        with pytest.raises(asyncio.CancelledError):
            await run_with_cleanup(
                engine=engine,
                progress=StringIO(),
                workload=workload,
                cleanup=cleanup,
            )

        cleanup.assert_awaited_once_with(engine=engine, progress=ANY)

    async def test_cancellation_and_cleanup_failure_preserve_both_errors(self) -> None:
        engine = Mock()
        workload: Callable[[], Awaitable[int]] = AsyncMock(
            side_effect=asyncio.CancelledError,
        )
        cleanup = AsyncMock(side_effect=RuntimeError("cleanup failed"))

        with pytest.raises(BaseExceptionGroup) as raised:
            await run_with_cleanup(
                engine=engine,
                progress=StringIO(),
                workload=workload,
                cleanup=cleanup,
            )

        assert any(isinstance(error, asyncio.CancelledError) for error in raised.value.exceptions)
        assert any(isinstance(error, RuntimeError) for error in raised.value.exceptions)
