from typing import Any

import pytest
from litestar import Litestar
from litestar.testing import TestClient
from pydantic import BaseModel, TypeAdapter

from entrypoints.litestar.api.schemas import CamelCaseSchema, RootSchema


class TestOpenApiContract:
    @staticmethod
    def api_models() -> list[type[BaseModel]]:
        models: list[type[BaseModel]] = []
        pending = [*CamelCaseSchema.__subclasses__(), *RootSchema.__subclasses__()]
        while pending:
            model = pending.pop()
            models.append(model)
            pending.extend(model.__subclasses__())
        return models

    def test_field_examples_validate_against_their_declared_types(self) -> None:
        errors: list[str] = []
        for model in self.api_models():
            for name, field in model.model_fields.items():
                for example in field.examples or ():
                    try:
                        TypeAdapter(field.rebuild_annotation()).validate_python(example)
                    except ValueError as error:
                        errors.append(f"{model.__name__}.{name}: {error}")

        assert errors == []

    def test_json_request_examples_validate_against_current_models(self, app: Litestar) -> None:
        schema = app.openapi_schema.to_schema()
        models = {model.__name__: model for model in self.api_models()}
        for path, path_item in schema["paths"].items():
            for method in ("post", "put", "patch"):
                operation = path_item.get(method, {})
                body = operation.get("requestBody", {})
                media = body.get("content", {}).get("application/json")
                if media is None:
                    continue
                assert body.get("description"), f"{method} {path}: missing body description"
                assert media.get("examples"), f"{method} {path}: missing body examples"
                model_name = media["schema"]["$ref"].rsplit("/", 1)[-1]
                for example in media["examples"].values():
                    models[model_name].model_validate(example["value"])

    @pytest.mark.parametrize(
        "query",
        [
            "",
            "?page=1",
            "?pageSize=20",
            "?page=0&pageSize=20",
            "?page=1&pageSize=0",
            "?page=1&pageSize=101",
            "?page=abc&pageSize=20",
        ],
    )
    def test_pagination_errors_match_documented_contract(
        self,
        app: Litestar,
        client: TestClient,
        query: str,
    ) -> None:
        operation = app.openapi_schema.to_schema()["paths"]["/api/resumes"]["get"]
        parameters = {item["name"]: item for item in operation["parameters"]}
        for name in ("page", "pageSize"):
            assert parameters[name]["required"] is True
            assert "default" not in parameters[name]["schema"]
            assert parameters[name]["schema"]["minimum"] == 1
        assert parameters["pageSize"]["schema"]["maximum"] == 100
        response = client.get("/api/resumes" + query)
        assert response.status_code == 400
        assert response.headers["content-type"].startswith("application/json")
        error_schema = app.openapi_schema.to_schema()["components"]["schemas"]["ErrorResponse"]
        error: dict[str, Any] = response.json()
        assert set(error_schema["required"]) <= error.keys()
        assert set(error) <= error_schema["properties"].keys()
        assert not {"detail", "status_code", "extra"} & error.keys()
        for child in error.get("nested_errors", []):
            assert set(error_schema["required"]) <= child.keys()

    def test_binary_responses_list_real_mime_types_and_download_headers(
        self,
        app: Litestar,
    ) -> None:
        paths = app.openapi_schema.to_schema()["paths"]
        export = paths["/api/resumes/{resume_id}/export"]["post"]["responses"]["200"]
        assert set(export["content"]) == {
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        assert {"Content-Disposition", "X-Resume-Page-Count"} <= export["headers"].keys()
        photo = paths["/api/resumes/{resume_id}/photo"]["get"]["responses"]["200"]
        assert set(photo["content"]) == {"image/jpeg"}
        content = paths["/api/knowledge/files/{file_id}/content"]["get"]["responses"]["200"]
        assert set(content["content"]) == {"image/webp", "application/octet-stream"}
        for response in (export, photo, content):
            for media in response["content"].values():
                assert media["schema"]["type"] == "string"
                assert media["schema"]["format"] == "binary"

    def test_multipart_file_parts_document_supported_mime_types(self, app: Litestar) -> None:
        paths = app.openapi_schema.to_schema()["paths"]
        cases = (
            ("/api/resumes/{resume_id}/photo", "post", "image/jpeg"),
            ("/api/knowledge/people/{person_id}/photo", "put", "image/jpeg, image/png, image/webp"),
            (
                "/api/knowledge/items/{item_id}/editor-images",
                "post",
                "image/jpeg, image/png, image/webp",
            ),
            ("/api/knowledge/items/{item_id}/attachments", "post", "*/*"),
        )
        for path, method, content_type in cases:
            multipart = paths[path][method]["requestBody"]["content"]["multipart/form-data"]
            assert multipart["encoding"]["file"]["contentType"] == content_type

    def test_error_examples_preserve_required_nullable_fields(self, app: Litestar) -> None:
        schema = app.openapi_schema.to_schema()
        required = set(schema["components"]["schemas"]["ErrorResponse"]["required"])
        for path_item in schema["paths"].values():
            for method in ("get", "post", "put", "patch", "delete"):
                operation = path_item.get(method, {})
                for status, response in operation.get("responses", {}).items():
                    if int(status) < 400:
                        continue
                    for example in response["content"]["application/json"]["examples"].values():
                        assert required <= example["value"].keys()
                        assert example["value"]["location"] is None or isinstance(
                            example["value"]["location"],
                            str,
                        )
                        assert example["value"]["attr"] is None or isinstance(
                            example["value"]["attr"],
                            str,
                        )

    def test_errors_and_conflicts_are_explicit_without_spurious_statuses(
        self,
        app: Litestar,
    ) -> None:
        paths = app.openapi_schema.to_schema()["paths"]
        for path_item in paths.values():
            for method in ("get", "post", "put", "patch", "delete"):
                operation = path_item.get(method)
                if operation is None:
                    continue
                assert {"401", "403", "500"} <= operation["responses"].keys()
                for code, response in operation["responses"].items():
                    if int(code) >= 400:
                        assert response["content"]["application/json"]["schema"] == {
                            "$ref": "#/components/schemas/ErrorResponse",
                        }
        transaction = paths["/api/finance/current-month/transactions/{transaction_id}"]
        assert "409" in transaction["put"]["responses"]
        for path in ("/api/knowledge/people", "/api/knowledge/dates"):
            assert "404" in paths[path]["get"]["responses"]
        assert "409" not in paths["/api/resumes"]["get"]["responses"]
        assert (
            paths["/api/resumes/{resume_id}"]["delete"]["responses"]["204"].get("content") is None
        )
