from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from entrypoints.litestar.lifespan.main import app_lifespan


async def test_app_lifespan_initializes_runtime_and_closes_dishka_container() -> None:
    container = SimpleNamespace(close=AsyncMock())
    app = SimpleNamespace(state=SimpleNamespace(dishka_container=container))

    with patch("entrypoints.litestar.lifespan.main.before_app_create") as before_app_create:
        async with app_lifespan(app):  # type: ignore[arg-type]
            before_app_create.assert_called_once_with()
            container.close.assert_not_awaited()

    container.close.assert_awaited_once_with()
