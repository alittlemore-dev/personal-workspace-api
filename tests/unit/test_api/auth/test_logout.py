from dishka import AsyncContainer
from litestar.testing import TestClient
from verbose_http_exceptions import status

from tests.unit.conftest import build_test_app


class TestLogoutApi:
    def test_logout_requires_authenticated_csrf_protected_request_and_clears_session(
        self,
        container: AsyncContainer,
    ) -> None:
        app = build_test_app(container=container, extra_middlewares=[])

        with TestClient(app) as client:
            login_response = client.post(
                "/api/auth/login",
                json={"username": "test-owner", "password": "test-owner-password"},
            )
            session_response = client.get("/api/auth/session")
            csrf_token = client.cookies["XSRF-TOKEN"]
            csrf_failure = client.post("/api/auth/logout")
            response = client.post("/api/auth/logout", headers={"X-XSRF-TOKEN": csrf_token})
            restored_session_response = client.get("/api/auth/session")

        assert login_response.status_code == status.HTTP_200_OK
        assert session_response.status_code == status.HTTP_200_OK
        assert csrf_failure.status_code == status.HTTP_403_FORBIDDEN
        assert csrf_failure.headers["cache-control"] == "no-store"
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["cache-control"] == "no-store"
        assert restored_session_response.status_code == status.HTTP_401_UNAUTHORIZED
        assert restored_session_response.headers["cache-control"] == "no-store"
        session_cookie = next(
            value
            for value in response.headers.get_list("set-cookie")
            if value.startswith("personal_workspace_session=")
        )
        assert "Max-Age" not in session_cookie
