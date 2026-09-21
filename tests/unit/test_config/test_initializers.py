import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from infra.config import initializers


def test_init_sentry_is_disabled_for_local_runtime() -> None:
    with (
        patch("infra.config.initializers.settings.sentry.use", False),
        patch("infra.config.initializers.sentry_sdk.init") as init,
    ):
        initializers.init_sentry()

    init.assert_not_called()


def test_init_sentry_uses_the_configured_dsn() -> None:
    with (
        patch("infra.config.initializers.settings.sentry.use", True),
        patch("infra.config.initializers.settings.sentry.dsn", "https://public@sentry.test/1"),
        patch("infra.config.initializers.sentry_sdk.init") as init,
    ):
        initializers.init_sentry()

    assert init.call_args.kwargs["dsn"] == "https://public@sentry.test/1"
    assert init.call_args.kwargs["send_default_pii"] is True
    assert len(init.call_args.kwargs["integrations"]) == 1


def test_before_app_create_migrates_and_starts_lag_monitor() -> None:
    loop = Mock()

    async def monitor() -> None:
        return None

    coroutine = monitor()
    with (
        patch("infra.config.initializers.asyncio.get_running_loop", return_value=loop),
        patch.object(initializers, "init_sentry") as init_sentry,
        patch.object(initializers, "migrate") as migrate,
        patch.object(initializers, "monitor_event_loop_lag", new=Mock(return_value=coroutine)),
    ):
        initializers.before_app_create()

    init_sentry.assert_called_once_with()
    migrate.assert_called_once_with("head")
    loop.create_task.assert_called_once_with(coroutine)
    coroutine.close()


async def test_lag_monitor_reports_running_coroutines_when_endpoint_is_not_detected() -> None:
    loop = Mock()
    loop.time.side_effect = [0.0, 2.5, 2.5]
    loop.is_running.side_effect = [True, False]
    task = Mock()
    task._coro = SimpleNamespace(  # noqa: SLF001
        cr_code=SimpleNamespace(co_qualname="worker.run", co_name="run"),
    )
    logger = Mock()

    with (
        patch("infra.config.initializers.asyncio.sleep", AsyncMock()),
        patch("infra.config.initializers.asyncio.all_tasks", return_value={task}),
        patch.object(initializers, "logger", logger),
    ):
        await initializers.monitor_event_loop_lag(loop)

    assert logger.warning.call_count == 2
    assert logger.warning.call_args_list[0].args == (
        "Call graph with running endpoint not detected. Maybe it changed due to framework update",
    )
    assert logger.warning.call_args_list[1].args == ("Event loop has lag",)
    assert logger.warning.call_args_list[1].kwargs["coroutine_names"] == "worker.run"


async def test_lag_monitor_formats_the_running_endpoint_call_graph() -> None:
    loop = Mock()
    loop.time.side_effect = [0.0, 2.5, 2.5]
    loop.is_running.side_effect = [True, False]
    endpoint_task = Mock()
    endpoint_task._coro = SimpleNamespace(  # noqa: SLF001
        cr_code=SimpleNamespace(
            co_qualname="RequestResponseCycle.run_asgi",
            co_name="run_asgi",
        ),
    )
    logger = Mock()

    with (
        patch.object(asyncio, "sleep", AsyncMock()),
        patch.object(asyncio, "all_tasks", return_value={endpoint_task}),
        patch.object(asyncio, "format_call_graph", return_value="request call graph") as formatter,
        patch.object(initializers, "logger", logger),
    ):
        await initializers.monitor_event_loop_lag(loop)

    formatter.assert_called_once_with(endpoint_task)
    logger.warning.assert_called_once_with(
        "Event loop has lag",
        lag=1.5,
        coroutine_names="RequestResponseCycle.run_asgi",
        call_graph="request call graph",
    )
