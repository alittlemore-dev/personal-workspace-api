from typing import Any

from litestar import Request, Response
from verbose_http_exceptions import (
    BadRequestHTTPException,
    ConflictHTTPException,
    InternalServerErrorHTTPException,
    NotFoundHTTPException,
    UnauthorizedHTTPException,
    status,
)
from verbose_http_exceptions.exc.base import BaseVerboseHTTPException, VerboseHTTPExceptionDict
from verbose_http_exceptions.ext.litestar import (
    ALL_EXCEPTION_HANDLERS_MAP,
    verbose_http_exception_handler,
)
from verbose_http_exceptions.ext.litestar.types import LitestarExceptionHandlersMap

from core.auth.exceptions import InvalidCredentialsError
from core.exceptions import DomainError, EntryNotFoundError
from core.files.exceptions import FileClientInternalError, FileInUseError, InvalidFileDataError
from core.knowledge.exceptions import InvalidKnowledgeDataError, KnowledgeConflictError
from infra.healthcheck import ReadinessCheckError

DOMAIN_ERROR_MAPPING: dict[type[DomainError], type[BaseVerboseHTTPException]] = {
    EntryNotFoundError: NotFoundHTTPException,
    InvalidFileDataError: BadRequestHTTPException,
    FileInUseError: BadRequestHTTPException,
    FileClientInternalError: InternalServerErrorHTTPException,
    InvalidKnowledgeDataError: BadRequestHTTPException,
    KnowledgeConflictError: ConflictHTTPException,
    InvalidCredentialsError: UnauthorizedHTTPException,
}


def find_verbose_exception_type(
    *,
    domain_error: DomainError,
) -> type[BaseVerboseHTTPException]:
    for domain_error_type, verbose_exception_type in DOMAIN_ERROR_MAPPING.items():
        if isinstance(domain_error, domain_error_type):
            return verbose_exception_type
    return InternalServerErrorHTTPException


def create_verbose_exception[VerboseHTTPExceptionT: BaseVerboseHTTPException](
    *,
    domain_error: DomainError,
    verbose_exception_type: type[VerboseHTTPExceptionT],
) -> VerboseHTTPExceptionT:
    message = (
        InternalServerErrorHTTPException.message
        if verbose_exception_type.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR
        else domain_error.message
    )
    return verbose_exception_type(message=message)


def domain_to_verbose_response_handler(
    request: Request[Any, Any, Any],
    exc: Exception,
) -> Response[VerboseHTTPExceptionDict]:
    if not isinstance(exc, DomainError):
        return unexpected_exception_handler(request, exc)
    return verbose_http_exception_handler(
        request,
        create_verbose_exception(
            domain_error=exc,
            verbose_exception_type=find_verbose_exception_type(domain_error=exc),
        ),
    )


def unexpected_exception_handler(
    request: Request[Any, Any, Any],
    _exc: Exception,
) -> Response[VerboseHTTPExceptionDict]:
    return verbose_http_exception_handler(
        request,
        InternalServerErrorHTTPException(
            message=InternalServerErrorHTTPException.message,
        ),
    )


def readiness_check_error_handler(
    _request: Request[Any, Any, Any],
    _exc: Exception,
) -> Response[str]:
    return Response(content="", status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


def get_litestar_exception_handlers() -> LitestarExceptionHandlersMap:
    return {
        **ALL_EXCEPTION_HANDLERS_MAP,
        Exception: unexpected_exception_handler,
        DomainError: domain_to_verbose_response_handler,
        ReadinessCheckError: readiness_check_error_handler,
    }
