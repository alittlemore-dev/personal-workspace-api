from unittest.mock import AsyncMock, Mock, patch

from litestar.middleware.logging import LoggingMiddleware

from entrypoints.litestar.initializers.main import create_logging_middleware_config
from entrypoints.litestar.middlewares.logging import PrivacySafeLoggingMiddleware


def test_request_logging_excludes_raw_query_values() -> None:
    config = create_logging_middleware_config()

    assert config.request_log_fields == ("path", "method", "path_params")
    assert config.middleware_class is PrivacySafeLoggingMiddleware


async def test_request_logging_redacts_private_knowledge_path_and_parameters() -> None:
    middleware = PrivacySafeLoggingMiddleware(
        app=AsyncMock(),
        config=create_logging_middleware_config(),
    )
    request = Mock()
    request.url.path = "/api/knowledge/people/11111111111111111111111111111111"

    with patch.object(
        LoggingMiddleware,
        "extract_request_data",
        new=AsyncMock(
            return_value={
                "message": "HTTP Request",
                "path": request.url.path,
                "method": "GET",
                "path_params": {"person_id": "1" * 32},
            },
        ),
    ):
        result = await middleware.extract_request_data(request=request)

    assert result == {
        "message": "HTTP Request",
        "path": "/api/knowledge/{private}",
        "method": "GET",
        "path_params": {},
    }


async def test_request_logging_keeps_non_knowledge_route_path() -> None:
    middleware = PrivacySafeLoggingMiddleware(
        app=AsyncMock(),
        config=create_logging_middleware_config(),
    )
    request = Mock()
    request.url.path = "/api/healthcheck"
    extracted = {
        "message": "HTTP Request",
        "path": request.url.path,
        "method": "GET",
        "path_params": {},
    }

    with patch.object(
        LoggingMiddleware,
        "extract_request_data",
        new=AsyncMock(return_value=extracted),
    ):
        result = await middleware.extract_request_data(request=request)

    assert result == extracted
