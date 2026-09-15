import pytest
from dishka import AsyncContainer
from litestar.testing import TestClient
from verbose_http_exceptions import status

from infra.config.settings import settings
from tests.unit.conftest import build_test_app

DOCS_PATHS = (
    "/api/docs",
    "/api/docs/swagger",
    "/api/docs/openapi.json",
    "/api/docs/oauth2-redirect.html",
)


class TestSessionApi:
    def test_session_rehydrates_user_and_establishes_angular_csrf_cookie(
        self,
        container: AsyncContainer,
    ) -> None:
        app = build_test_app(container=container, extra_middlewares=[])

        with TestClient(app) as client:
            login_response = client.post(
                "/api/auth/login",
                json={"username": "test-owner", "password": "test-owner-password"},
            )
            response = client.get("/api/auth/session")

        assert login_response.status_code == status.HTTP_200_OK
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"username": "test-owner"}
        assert response.headers["cache-control"] == "no-store"
        csrf_cookie = next(
            value
            for value in response.headers.get_list("set-cookie")
            if value.startswith("XSRF-TOKEN=")
        )
        assert "HttpOnly" not in csrf_cookie
        assert "Path=/" in csrf_cookie
        assert "SameSite=strict" in csrf_cookie

    def test_private_routes_reject_missing_sessions(
        self,
        container: AsyncContainer,
    ) -> None:
        app = build_test_app(container=container, extra_middlewares=[])

        with TestClient(app) as client:
            for path in (
                "/api/tools/cache",
                "/api/auth/session",
                *DOCS_PATHS,
            ):
                response = client.get(path)
                assert response.status_code == status.HTTP_401_UNAUTHORIZED
                assert response.headers["cache-control"] == "no-store"

            logout_response = client.post("/api/auth/logout")
            assert logout_response.status_code == status.HTTP_401_UNAUTHORIZED
            assert logout_response.headers["cache-control"] == "no-store"

    def test_public_healthcheck_and_i18n_do_not_require_a_session(
        self,
        container: AsyncContainer,
    ) -> None:
        app = build_test_app(container=container, extra_middlewares=[])

        with TestClient(app) as client:
            health_response = client.get("/api/healthcheck")
            i18n_response = client.get("/api/i18n/languages")

        assert health_response.status_code == status.HTTP_200_OK
        assert i18n_response.status_code == status.HTTP_200_OK
        assert health_response.headers.get("cache-control") != "no-store"
        assert i18n_response.headers.get("cache-control") != "no-store"

    def test_boundary_like_unknown_paths_remain_public_not_found(
        self,
        container: AsyncContainer,
    ) -> None:
        app = build_test_app(container=container, extra_middlewares=[])

        with TestClient(app) as client:
            for path in ("/api/authors", "/api/docs-old", "/api/administrator", "/api/toolbox"):
                response = client.get(path)
                assert response.status_code == status.HTTP_404_NOT_FOUND
                assert response.headers.get("cache-control") != "no-store"

    def test_legacy_admin_url_is_not_registered_for_an_authenticated_user(
        self,
        container: AsyncContainer,
    ) -> None:
        app = build_test_app(container=container, extra_middlewares=[])

        with TestClient(app) as client:
            login_response = client.post(
                "/api/auth/login",
                json={"username": "test-owner", "password": "test-owner-password"},
            )
            response = client.get("/api/admin/tools/cache")

        assert login_response.status_code == status.HTTP_200_OK
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.headers.get("cache-control") != "no-store"

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("GET", "/api/tools/cache"),
            ("GET", "/api/auth/session"),
            ("POST", "/api/auth/logout"),
            *(("GET", path) for path in DOCS_PATHS),
        ],
    )
    @pytest.mark.parametrize("cookie_state", ["expired", "tampered", "malformed"])
    def test_protected_routes_reject_untrusted_session_cookies(
        self,
        container: AsyncContainer,
        monkeypatch: pytest.MonkeyPatch,
        method: str,
        path: str,
        cookie_state: str,
    ) -> None:
        initial_timestamp = 1_000_000
        if cookie_state == "expired":
            monkeypatch.setattr(
                "litestar.middleware.session.client_side.time.time",
                lambda: initial_timestamp,
            )
        app = build_test_app(container=container, extra_middlewares=[])

        with TestClient(app) as client:
            login_response = client.post(
                "/api/auth/login",
                json={"username": "test-owner", "password": "test-owner-password"},
            )
            if cookie_state == "expired":
                monkeypatch.setattr(
                    "litestar.middleware.session.client_side.time.time",
                    lambda: initial_timestamp + settings.auth.session_ttl_seconds + 1,
                )
            elif cookie_state == "tampered":
                session_value = client.cookies["personal_workspace_session"]
                tampered_value = f"{session_value[:-1]}{'A' if session_value[-1] != 'A' else 'B'}"
                client.cookies.set("personal_workspace_session", tampered_value)
            else:
                client.cookies.set("personal_workspace_session", "malformed")
            response = client.request(method, path)

        assert login_response.status_code == status.HTTP_200_OK
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.headers["cache-control"] == "no-store"

    def test_authenticated_docs_are_not_cached(
        self,
        container: AsyncContainer,
    ) -> None:
        app = build_test_app(container=container, extra_middlewares=[])

        with TestClient(app) as client:
            login_response = client.post(
                "/api/auth/login",
                json={"username": "test-owner", "password": "test-owner-password"},
            )
            for path in DOCS_PATHS:
                response = client.get(path)

                assert response.status_code == status.HTTP_200_OK
                assert response.headers["cache-control"] == "no-store"

        assert login_response.status_code == status.HTTP_200_OK
