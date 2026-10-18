from dataclasses import dataclass
from functools import cache
from typing import cast

from litestar import Litestar
from litestar._openapi.plugin import OpenAPIPlugin
from litestar.handlers.http_handlers import HTTPRouteHandler
from litestar.openapi.spec import Encoding, Example, OpenAPI, Operation, RequestBody
from litestar.params import BodyKwarg
from litestar.routes.http import HTTPRoute

from entrypoints.litestar.openapi_responses import (
    BinaryResponseMetadata,
    apply_binary_response_metadata,
    apply_error_response_metadata,
    install_error_response_schema,
)


@dataclass(frozen=True)
class RequestBodyMetadata:
    description: str
    examples: dict[str, Example]


@cache
def install_openapi_request_body_metadata() -> None:
    build_openapi = OpenAPIPlugin._build_openapi  # noqa: SLF001

    def build_openapi_with_request_body_metadata(plugin: OpenAPIPlugin) -> OpenAPI:
        openapi_schema = build_openapi(plugin)
        apply_openapi_request_body_metadata(app=plugin.app, openapi_schema=openapi_schema)
        return openapi_schema

    setattr(  # noqa: B010
        OpenAPIPlugin,
        "_build_openapi",
        build_openapi_with_request_body_metadata,
    )


def apply_openapi_request_body_metadata(
    *,
    app: Litestar,
    openapi_schema: OpenAPI,
) -> None:
    if openapi_schema.paths is None:
        return

    install_error_response_schema(openapi_schema=openapi_schema)
    for route in app.routes:
        if not isinstance(route, HTTPRoute) or route.path_format is None:
            continue
        path_item = openapi_schema.paths.get(route.path_format)
        if path_item is None:
            continue
        for route_handler in route.route_handlers:
            metadata = get_request_body_metadata(route_handler=route_handler)
            for method in route_handler.http_methods:
                operation = cast("Operation | None", getattr(path_item, method.lower()))
                if operation is None:
                    continue
                apply_error_response_metadata(
                    operation=operation,
                    statuses=route_handler.opt.get("error_statuses", ()),
                )
                binary_response = route_handler.opt.get("binary_response")
                if isinstance(binary_response, BinaryResponseMetadata):
                    apply_binary_response_metadata(operation=operation, metadata=binary_response)
                apply_upload_metadata(
                    operation=operation,
                    media_types=route_handler.opt.get("upload_media_types", ()),
                )
                if metadata is not None:
                    apply_request_body_metadata(operation=operation, metadata=metadata)


def get_request_body_metadata(*, route_handler: HTTPRouteHandler) -> RequestBodyMetadata | None:
    signatures = [route_handler.parsed_fn_signature]
    signatures.extend(
        provider.parsed_fn_signature
        for provider in route_handler.resolve_dependencies().values()
        if hasattr(provider, "parsed_fn_signature")
    )
    for signature in signatures:
        data_field = signature.parameters.get("data")
        if data_field is not None and isinstance(data_field.kwarg_definition, BodyKwarg):
            metadata = build_request_body_metadata(body_kwarg=data_field.kwarg_definition)
            if metadata is not None:
                return metadata
    return None


def build_request_body_metadata(body_kwarg: BodyKwarg) -> RequestBodyMetadata | None:
    if body_kwarg.description is None or body_kwarg.examples is None:
        return None
    return RequestBodyMetadata(
        description=body_kwarg.description,
        examples=format_request_body_examples(examples=body_kwarg.examples),
    )


def format_request_body_examples(*, examples: list[Example]) -> dict[str, Example]:
    return {
        example.id or f"example{index}": example for index, example in enumerate(examples, start=1)
    }


def apply_request_body_metadata(
    *,
    operation: Operation,
    metadata: RequestBodyMetadata,
) -> None:
    if not isinstance(operation.request_body, RequestBody):
        return

    request_body = operation.request_body
    if request_body.description is None:
        request_body.description = metadata.description
    for media_type_schema in request_body.content.values():
        if media_type_schema.examples is None:
            media_type_schema.examples = dict(metadata.examples)


def apply_upload_metadata(*, operation: Operation, media_types: tuple[str, ...]) -> None:
    if not media_types or not isinstance(operation.request_body, RequestBody):
        return
    multipart = operation.request_body.content.get("multipart/form-data")
    if multipart is not None:
        multipart.encoding = {"file": Encoding(content_type=", ".join(media_types))}
