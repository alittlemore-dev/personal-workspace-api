from collections.abc import Iterable, Mapping
from typing import Any

from backend_sdk.auth.testing import FakeAuthenticationClient
from backend_sdk.integrations.litestar import AuthPlugin
from dishka import AsyncContainer
from litestar import Litestar
from litestar.testing import TestClient

from entrypoints.litestar.initializers.main import create_litestar_app


class TestOpenApiMetadata:
    def test_public_schema_exposes_user_routes_and_excludes_service_and_admin_routes(
        self,
        app: Litestar,
    ) -> None:
        schema = app.openapi_schema.to_schema()
        paths = schema["paths"]

        assert "/api/resumes" in paths
        assert "/api/calendar" in paths
        assert "/api/telegram" in paths
        assert any(path.startswith("/api/knowledge/") for path in paths)
        assert not any(
            path.startswith(("/api/tools", "/api/internal", "/api/healthcheck")) for path in paths
        )
        assert "/api/telegram/webhook" not in paths
        for _, _, operation in self._iter_operations(schema=schema):
            assert operation["security"] == [{"bearerAuth": []}]

    def test_schema_is_anonymous_with_real_auth_plugin(self, container: AsyncContainer) -> None:
        authentication_client = FakeAuthenticationClient()
        app = create_litestar_app(
            lifespan=[],
            container=container,
            extra_plugins=[AuthPlugin(auth_client=authentication_client)],
            extra_middlewares=[],
        )
        with TestClient(app) as client:
            response = client.get("/api/docs/openapi.json")
            assert response.status_code == 200
            assert "/api/resumes" in response.json()["paths"]
            assert (
                response.json()["components"]["securitySchemes"]["bearerAuth"]["bearerFormat"]
                == "PASETO"
            )
            assert client.get("/api/resumes").status_code == 401
        assert authentication_client.tokens == ()

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
