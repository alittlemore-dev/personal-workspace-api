from datetime import UTC, date, datetime

import pytest
from backend_sdk import RoleEnum
from backend_sdk.auth.testing import FakeAuthenticationClient, bearer_headers
from backend_sdk.integrations.litestar import AuthPlugin
from dishka import AsyncContainer
from httpx import codes
from litestar.testing import TestClient

from core.cache_tools.enums import CacheWarmOperationStatusEnum
from core.cache_tools.schemas import CacheWarmOperation
from core.calendar.enums import CalendarWindow
from core.calendar.schemas import Calendar, CalendarSummary
from core.wiki_links.schemas import WikiLinkTargets
from entrypoints.litestar.initializers.main import create_litestar_app
from tests.helpers.api import APIHelper
from tests.helpers.app import IocContainerHelper
from tests.helpers.factories.core import CoreFactoryHelper


def build_sdk_auth_app(
    *,
    container: AsyncContainer,
    auth_client: FakeAuthenticationClient,
) -> TestClient:
    app = create_litestar_app(
        lifespan=[],
        container=container,
        extra_plugins=[AuthPlugin(auth_client=auth_client)],
        extra_middlewares=[],
    )
    return TestClient(app)


class TestSdkAuthentication:
    @pytest.mark.parametrize("path", ["/api/vault/recent", "/api/vault/statistics"])
    def test_vault_requires_authentication(self, container: AsyncContainer, path: str) -> None:
        with build_sdk_auth_app(
            container=container,
            auth_client=FakeAuthenticationClient(),
        ) as client:
            response = client.get(path)
        assert response.status_code == codes.UNAUTHORIZED

    def test_allows_anonymous_health_requests(self, container: AsyncContainer) -> None:
        auth_client = FakeAuthenticationClient()
        auth_client.set_unavailable()

        with build_sdk_auth_app(container=container, auth_client=auth_client) as client:
            api = APIHelper(client=client)

            assert api.get_health().status_code == codes.OK
            assert api.get_health_ready().status_code == codes.OK

    def test_rejects_private_request_without_token(self, container: AsyncContainer) -> None:
        auth_client = FakeAuthenticationClient()

        with build_sdk_auth_app(container=container, auth_client=auth_client) as client:
            response = APIHelper(client=client).get_calendar(
                reference_date="2026-07-31",
                window="currentAndNextMonths",
            )

        assert response.status_code == codes.UNAUTHORIZED

    @pytest.mark.parametrize(
        "role",
        [RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.MODERATOR, RoleEnum.USER],
    )
    async def test_authenticated_principal_reaches_author_scoped_endpoint(
        self,
        container: AsyncContainer,
        role: RoleEnum,
    ) -> None:
        username = f"sdk-authenticated-{role.value}"
        auth_client = FakeAuthenticationClient(username=username, role=role)
        use_case = await IocContainerHelper(container=container).get_calendar_use_case()
        use_case.get_calendar.return_value = Calendar(
            reference_date=date(2026, 7, 31),
            window=CalendarWindow.CURRENT_AND_NEXT_MONTHS,
            summary=CalendarSummary(memorable_date_count=0, birthday_count=0),
            entries=[],
        )

        with build_sdk_auth_app(container=container, auth_client=auth_client) as client:
            response = client.get(
                "/api/calendar",
                params={
                    "referenceDate": "2026-07-31",
                    "window": "currentAndNextMonths",
                },
                headers=bearer_headers(token="valid-token"),  # noqa: S106
            )

        assert response.status_code == codes.OK
        assert use_case.get_calendar.call_args.kwargs["params"].author_username == username
        assert response.json() == {
            "referenceDate": "2026-07-31",
            "window": "currentAndNextMonths",
            "summary": {"memorableDateCount": 0, "birthdayCount": 0},
            "entries": [],
        }

    @pytest.mark.parametrize("role", [RoleEnum.ADMIN, RoleEnum.OWNER])
    async def test_admins_can_manage_cache(
        self,
        container: AsyncContainer,
        role: RoleEnum,
    ) -> None:
        auth_client = FakeAuthenticationClient(username="cache-manager", role=role)
        use_case = await IocContainerHelper(container=container).get_cache_tools_use_case()
        cache_status = CoreFactoryHelper.cache_tools_status()
        operation = CacheWarmOperation(
            operation_id="operation-id",
            status=CacheWarmOperationStatusEnum.QUEUED,
            queued_at=datetime(2026, 7, 16, 12, 0, tzinfo=UTC),
            summary=None,
        )
        use_case.get_status.return_value = cache_status
        use_case.clear.return_value = cache_status
        use_case.enqueue_manual_warm.return_value = operation
        use_case.get_manual_warm_operation.return_value = operation
        headers = bearer_headers(token="admin-token")  # noqa: S106

        with build_sdk_auth_app(container=container, auth_client=auth_client) as client:
            assert client.get("/api/tools/cache", headers=headers).status_code == codes.OK
            assert client.post("/api/tools/cache/clear", headers=headers).status_code == codes.OK
            warm_response = client.post("/api/tools/cache/warm", headers=headers)
            assert warm_response.status_code == codes.ACCEPTED
            operation_id = warm_response.json()["operationId"]
            poll_response = client.get(f"/api/tools/cache/warm/{operation_id}", headers=headers)
            assert poll_response.status_code == codes.OK
            assert poll_response.json()["status"] == "queued"

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("GET", "/api/tools/cache"),
            ("POST", "/api/tools/cache/clear"),
            ("POST", "/api/tools/cache/warm"),
            ("GET", "/api/tools/cache/warm/operation-id"),
        ],
    )
    def test_rejects_anonymous_cache_tools(
        self,
        container: AsyncContainer,
        method: str,
        path: str,
    ) -> None:
        auth_client = FakeAuthenticationClient()
        with build_sdk_auth_app(container=container, auth_client=auth_client) as client:
            response = client.request(method, path)
        assert response.status_code == codes.UNAUTHORIZED

    @pytest.mark.parametrize("role", [RoleEnum.USER, RoleEnum.MODERATOR])
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("GET", "/api/tools/cache"),
            ("POST", "/api/tools/cache/clear"),
            ("POST", "/api/tools/cache/warm"),
            ("GET", "/api/tools/cache/warm/operation-id"),
        ],
    )
    async def test_rejects_non_admin_cache_tools(
        self,
        container: AsyncContainer,
        role: RoleEnum,
        method: str,
        path: str,
    ) -> None:
        auth_client = FakeAuthenticationClient(username="workspace-reader", role=role)
        use_case = await IocContainerHelper(container=container).get_cache_tools_use_case()

        with build_sdk_auth_app(container=container, auth_client=auth_client) as client:
            response = client.request(
                method,
                path,
                headers=bearer_headers(token="reader-token"),  # noqa: S106
            )

        assert response.status_code == codes.FORBIDDEN
        use_case.get_status.assert_not_awaited()
        use_case.clear.assert_not_awaited()
        use_case.enqueue_manual_warm.assert_not_awaited()
        use_case.get_manual_warm_operation.assert_not_awaited()

    async def test_authenticated_response_disables_shared_caching(
        self,
        container: AsyncContainer,
    ) -> None:
        auth_client = FakeAuthenticationClient(
            username="private-owner",
            role=RoleEnum.OWNER,
        )
        use_case = await IocContainerHelper(container=container).get_wiki_links_use_case()
        use_case.list_targets.return_value = WikiLinkTargets(values=[])

        with build_sdk_auth_app(container=container, auth_client=auth_client) as client:
            response = client.get(
                "/api/wiki-links/targets",
                params={"language": "en"},
                headers=bearer_headers(token="private-token"),  # noqa: S106
            )

        assert response.status_code == codes.OK
        assert response.json() == {"targets": []}
        assert response.headers["cache-control"] == "no-store"

    def test_returns_service_unavailable_when_auth_service_is_unavailable(
        self,
        container: AsyncContainer,
    ) -> None:
        auth_client = FakeAuthenticationClient()
        auth_client.set_unavailable()

        with build_sdk_auth_app(container=container, auth_client=auth_client) as client:
            response = client.get(
                "/api/calendar",
                params={
                    "referenceDate": "2026-07-31",
                    "window": "currentAndNextMonths",
                },
                headers=bearer_headers(token="unverifiable-token"),  # noqa: S106
            )

        assert response.status_code == codes.SERVICE_UNAVAILABLE
