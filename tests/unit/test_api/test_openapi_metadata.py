from collections.abc import Iterable, Mapping
from typing import Any

from litestar import Litestar


class TestOpenApiMetadata:
    def test_public_schema_exposes_public_routes_and_excludes_protected_routes(
        self,
        app: Litestar,
    ) -> None:
        schema = app.openapi_schema.to_schema()
        paths = schema["paths"]

        assert set(paths) == {
            "/api/auth/login",
            "/api/auth/session",
            "/api/auth/logout",
            "/api/i18n/languages",
            "/api/i18n/bundles/{language}",
        }

    def test_visible_parameters_have_descriptions_and_examples(self, app: Litestar) -> None:
        schema = app.openapi_schema.to_schema()
        missing_metadata = [
            f"{method.upper()} {path} parameter {parameter['in']}:{parameter['name']}"
            for path, method, operation in self._iter_operations(schema=schema)
            for parameter in operation.get("parameters", ())
            if not parameter.get("description")
            or ("examples" not in parameter and "examples" not in parameter.get("schema", {}))
        ]

        assert missing_metadata == []

    @staticmethod
    def _iter_operations(
        *,
        schema: Mapping[str, Any],
    ) -> Iterable[tuple[str, str, Mapping[str, Any]]]:
        for path, path_schema in schema["paths"].items():
            for method, operation in path_schema.items():
                if method in {"get", "post", "put", "patch", "delete"}:
                    yield path, method, operation
