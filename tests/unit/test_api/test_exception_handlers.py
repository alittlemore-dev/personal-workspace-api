from collections.abc import Sequence

import pytest
from httpx import Response, codes
from litestar import Litestar, get
from litestar.testing import TestClient
from litestar.types import ControllerRouterHandler
from verbose_http_exceptions import InternalServerErrorHTTPException

from core.exceptions import DomainError, EntryNotFoundError
from core.files.exceptions import FileClientInternalError, FileInUseError, InvalidFileDataError
from core.knowledge.exceptions import InvalidKnowledgeDataError, KnowledgeConflictError
from entrypoints.litestar import exception_handlers
from entrypoints.litestar.exception_handlers import get_litestar_exception_handlers
from infra.healthcheck import ReadinessCheckError

PYTHON_ERROR_MESSAGE = "plain python error"


@get("/entry-not-found", sync_to_thread=False)
def raise_entry_not_found() -> None:
    raise EntryNotFoundError


@get("/invalid-file", sync_to_thread=False)
def raise_invalid_file() -> None:
    raise InvalidFileDataError


@get("/file-in-use", sync_to_thread=False)
def raise_file_in_use() -> None:
    raise FileInUseError


@get("/file-client", sync_to_thread=False)
def raise_file_client_error() -> None:
    raise FileClientInternalError(message="storage unavailable")


@get("/invalid-knowledge", sync_to_thread=False)
def raise_invalid_knowledge() -> None:
    raise InvalidKnowledgeDataError


@get("/knowledge-conflict", sync_to_thread=False)
def raise_knowledge_conflict() -> None:
    raise KnowledgeConflictError


@get("/python-error", sync_to_thread=False)
def raise_python_error() -> None:
    raise ValueError(PYTHON_ERROR_MESSAGE)


@get("/readiness", sync_to_thread=False)
def raise_readiness_error() -> None:
    raise ReadinessCheckError


@pytest.mark.parametrize(
    ("path", "expected_status", "expected_message"),
    [
        ("/entry-not-found", codes.NOT_FOUND, EntryNotFoundError.message),
        ("/invalid-file", codes.BAD_REQUEST, InvalidFileDataError.message),
        ("/file-in-use", codes.BAD_REQUEST, FileInUseError.message),
        (
            "/file-client",
            codes.INTERNAL_SERVER_ERROR,
            InternalServerErrorHTTPException.message,
        ),
        ("/invalid-knowledge", codes.BAD_REQUEST, InvalidKnowledgeDataError.message),
        ("/knowledge-conflict", codes.CONFLICT, KnowledgeConflictError.message),
    ],
)
def test_exception_handlers_return_stable_http_contract(
    path: str,
    expected_status: int,
    expected_message: str,
) -> None:
    response = get_response(path)

    assert response.status_code == expected_status
    assert response.json()["message"] == expected_message


def test_unhandled_exception_redacts_internal_message() -> None:
    response = get_response("/python-error")

    assert response.status_code == codes.INTERNAL_SERVER_ERROR
    assert response.json()["message"] == InternalServerErrorHTTPException.message
    assert PYTHON_ERROR_MESSAGE not in response.text


def test_domain_server_error_redacts_internal_message() -> None:
    response = get_response("/file-client")

    assert response.status_code == codes.INTERNAL_SERVER_ERROR
    assert response.json()["message"] == InternalServerErrorHTTPException.message
    assert "storage unavailable" not in response.text


def test_readiness_error_returns_empty_service_unavailable() -> None:
    response = get_response("/readiness")

    assert response.status_code == codes.SERVICE_UNAVAILABLE
    assert response.content == b""


def test_domain_errors_use_single_data_driven_handler() -> None:
    handlers = get_litestar_exception_handlers()

    assert handlers[DomainError] is exception_handlers.domain_to_verbose_response_handler


def get_response(path: str) -> Response:
    app = Litestar(
        route_handlers=list(exception_route_handlers()),
        exception_handlers=get_litestar_exception_handlers(),
    )
    with TestClient(app) as client:
        return client.get(path)


def exception_route_handlers() -> Sequence[ControllerRouterHandler]:
    return (
        raise_entry_not_found,
        raise_invalid_file,
        raise_file_in_use,
        raise_file_client_error,
        raise_invalid_knowledge,
        raise_knowledge_conflict,
        raise_python_error,
        raise_readiness_error,
    )
