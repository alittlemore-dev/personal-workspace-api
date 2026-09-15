import pytest
from dishka import AsyncContainer
from litestar.testing import TestClient
from verbose_http_exceptions import status

from infra.config.settings import SecretStrExtended, settings
from tests.unit.conftest import build_test_app


class TestLoginApi:
    def test_login_returns_owner_and_sets_secure_encrypted_session_cookie(
        self,
        container: AsyncContainer,
    ) -> None:
        app = build_test_app(container=container, extra_middlewares=[])

        with TestClient(app) as client:
            response = client.post(
                "/api/auth/login",
                json={"username": "test-owner", "password": "test-owner-password"},
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"username": "test-owner"}
        assert response.headers.get("cache-control") != "no-store"
        session_cookie = next(
            value
            for value in response.headers.get_list("set-cookie")
            if value.startswith("personal_workspace_session=")
        )
        assert "HttpOnly" in session_cookie
        assert "Max-Age=3600" in session_cookie
        assert "Path=/" in session_cookie
        assert "SameSite=strict" in session_cookie
        assert "Secure" not in session_cookie
        assert "test-owner" not in session_cookie

    def test_login_rejects_invalid_credentials_without_session_cookie(
        self,
        container: AsyncContainer,
    ) -> None:
        app = build_test_app(container=container, extra_middlewares=[])

        with TestClient(app) as client:
            response = client.post(
                "/api/auth/login",
                json={"username": "test-owner", "password": "wrong-password"},
            )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.headers.get("cache-control") != "no-store"
        assert not any(
            value.startswith("personal_workspace_session=")
            for value in response.headers.get_list("set-cookie")
        )

    def test_login_rejects_invalid_request_shape(self, container: AsyncContainer) -> None:
        app = build_test_app(container=container, extra_middlewares=[])

        with TestClient(app) as client:
            response = client.post("/api/auth/login", json={"username": "test-owner"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.headers.get("cache-control") != "no-store"

    def test_login_rejects_malformed_configured_password_hash(
        self,
        container: AsyncContainer,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings.owner, "password_hash", SecretStrExtended("malformed"))
        app = build_test_app(container=container, extra_middlewares=[])

        with TestClient(app) as client:
            response = client.post(
                "/api/auth/login",
                json={"username": "test-owner", "password": "test-owner-password"},
            )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.headers.get("cache-control") != "no-store"
        assert not any(
            value.startswith("personal_workspace_session=")
            for value in response.headers.get_list("set-cookie")
        )

    def test_login_sets_secure_session_and_csrf_cookies_over_https(
        self,
        container: AsyncContainer,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings.app, "url_schema", "https")
        app = build_test_app(container=container, extra_middlewares=[])

        with TestClient(app, base_url="https://testserver.local") as client:
            login_response = client.post(
                "/api/auth/login",
                json={"username": "test-owner", "password": "test-owner-password"},
            )
            session_response = client.get("/api/auth/session")

        session_cookie = next(
            value
            for value in login_response.headers.get_list("set-cookie")
            if value.startswith("personal_workspace_session=")
        )
        csrf_cookie = next(
            value
            for value in session_response.headers.get_list("set-cookie")
            if value.startswith("XSRF-TOKEN=")
        )
        assert login_response.status_code == status.HTTP_200_OK
        assert session_response.status_code == status.HTTP_200_OK
        assert "Secure" in session_cookie
        assert "Secure" in csrf_cookie
