from dataclasses import dataclass

from litestar import status_codes
from litestar.openapi.spec import (
    Components,
    Example,
    OpenAPI,
    OpenAPIHeader,
    OpenAPIMediaType,
    OpenAPIResponse,
    Operation,
    Reference,
    Schema,
)
from litestar.openapi.spec.enums import OpenAPIFormat, OpenAPIType
from verbose_http_exceptions import error_by_status_mapping
from verbose_http_exceptions.ext.litestar.exc import ValidationHTTPException

from entrypoints.litestar.openapi_examples import JSONExample


@dataclass(frozen=True)
class BinaryResponseMetadata:
    media_types: tuple[str, ...]
    description: str
    headers: dict[str, OpenAPIHeader | Reference]


def apply_binary_response_metadata(
    *,
    operation: Operation,
    metadata: BinaryResponseMetadata,
) -> None:
    if operation.responses is None:
        return
    operation.responses["200"] = OpenAPIResponse(
        description=metadata.description,
        content={
            media_type: OpenAPIMediaType(
                schema=Schema(
                    type=OpenAPIType.STRING,
                    format=OpenAPIFormat.BINARY,
                    content_media_type=media_type,
                    description="Raw file bytes. Save the response body as a file.",
                ),
            )
            for media_type in metadata.media_types
        },
        headers=metadata.headers,
    )


def install_error_response_schema(*, openapi_schema: OpenAPI) -> None:
    if openapi_schema.components is None:
        openapi_schema.components = Components()
    if openapi_schema.components.schemas is None:
        openapi_schema.components.schemas = {}
    openapi_schema.components.schemas["ErrorResponse"] = Schema(
        type=OpenAPIType.OBJECT,
        description=(
            "Application error. Use code and type for programmatic handling; message is "
            "human-readable and may vary. location and attr are null for errors unrelated "
            "to a specific request field. A single validation error may be returned directly; "
            "multiple errors are grouped in nested_errors. Error keys use snake_case."
        ),
        required=["code", "type", "message", "location", "attr"],
        properties={
            "code": Schema(
                type=OpenAPIType.STRING,
                description="Error family.",
                examples=["validation_error"],
            ),
            "type": Schema(
                type=OpenAPIType.STRING,
                description="Specific error kind.",
                examples=["missing"],
            ),
            "message": Schema(
                type=OpenAPIType.STRING,
                description="Human-readable explanation.",
                examples=["Field required"],
            ),
            "location": Schema(
                type=[OpenAPIType.STRING, OpenAPIType.NULL],
                description="Request source, such as query or body; null if not field-specific.",
                examples=["query", None],
            ),
            "attr": Schema(
                type=[OpenAPIType.STRING, OpenAPIType.NULL],
                description="Field path reported by the validator; null if not field-specific.",
                examples=["pageSize", None],
            ),
            "nested_errors": Schema(
                type=OpenAPIType.ARRAY,
                description=(
                    "Individual validation failures; omitted when there are no nested errors."
                ),
                items=Reference(ref="#/components/schemas/ErrorResponse"),
            ),
        },
    )


def apply_error_response_metadata(
    *,
    operation: Operation,
    statuses: tuple[int, ...],
) -> None:
    if operation.responses is None:
        operation.responses = {}
    descriptions = {
        400: (
            "Invalid request: missing required parameters, invalid field values, "
            "or a domain validation error. See location, attr, and nested_errors "
            "for details."
        ),
        401: "Missing, invalid, expired, or revoked bearer credential.",
        403: (
            "Authenticated caller lacks the required role or personal API token "
            "permission, or the requested action is forbidden."
        ),
        404: "Resource does not exist or is outside the authenticated user’s workspace.",
        409: (
            "The requested change conflicts with current state, such as a stale transaction "
            "version or a duplicate knowledge label. Resolve the conflict before retrying."
        ),
        413: "Request body exceeds this operation’s upload limit.",
        500: "Unexpected server error. Retry later; internal details are not exposed.",
        503: (
            "Authentication, account settings, currency rates, or Telegram service is "
            "temporarily unavailable."
        ),
    }
    response_statuses = set(statuses) | {
        int(value)
        for value in operation.responses
        if value.isdigit() and int(value) >= status_codes.HTTP_400_BAD_REQUEST
    }
    if operation.security:
        response_statuses.update((401, 403, 503))
    response_statuses.add(500)
    for status in sorted(response_statuses):
        exception = error_by_status_mapping[status]()
        examples: dict[str, Example | Reference] = {"error": JSONExample(value=exception.as_dict())}
        if status == status_codes.HTTP_400_BAD_REQUEST and any(
            parameter.name == "pageSize"
            for parameter in operation.parameters or ()
            if not isinstance(parameter, Reference)
        ):
            examples["missingPageSize"] = JSONExample(
                summary="Missing required pagination parameter (on paginated list operations)",
                value=ValidationHTTPException(
                    message="Missing required query parameter 'pageSize'",
                    location="query",
                    attr_name="pageSize",
                    type_="missing",
                ).as_dict(),
            )
        operation.responses[str(status)] = OpenAPIResponse(
            description=descriptions[status],
            content={
                "application/json": OpenAPIMediaType(
                    schema=Reference(ref="#/components/schemas/ErrorResponse"),
                    examples=examples,
                ),
            },
        )
