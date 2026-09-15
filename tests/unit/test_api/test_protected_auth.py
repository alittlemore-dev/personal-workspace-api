from dishka import AsyncContainer
from litestar.testing import TestClient
from verbose_http_exceptions import status

from tests.unit.conftest import build_test_app


def test_protected_api_rejects_request_without_authenticated_session(
    container: AsyncContainer,
) -> None:
    app = build_test_app(container=container, extra_middlewares=[])

    with TestClient(app) as client:
        response = client.get("/api/tools/cache")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
