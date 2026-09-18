from datetime import date

from backend_sdk import RoleEnum
from backend_sdk.auth.testing import FakeAuthenticationClient, bearer_headers
from backend_sdk.integrations.litestar import AuthPlugin
from dishka import AsyncContainer
from httpx import codes
from litestar.testing import TestClient

from core.calendar.enums import CalendarWindow
from core.calendar.schemas import Calendar, CalendarSummary
from core.wiki_links.schemas import WikiLinkTargets
from entrypoints.litestar.initializers.main import create_litestar_app
from tests.helpers.api import APIHelper
from tests.helpers.app import IocContainerHelper


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
    def test_allows_anonymous_health_and_i18n_requests(self, container: AsyncContainer) -> None:
        auth_client = FakeAuthenticationClient()
        auth_client.set_unavailable()

        with build_sdk_auth_app(container=container, auth_client=auth_client) as client:
            api = APIHelper(client=client)

            assert api.get_health().status_code == codes.OK
            assert api.get_health_ready().status_code == codes.OK
            assert api.get_i18n_languages().status_code == codes.OK
            assert api.get_i18n_bundle(language="en").status_code == codes.OK

    def test_rejects_private_request_without_token(self, container: AsyncContainer) -> None:
        auth_client = FakeAuthenticationClient()

        with build_sdk_auth_app(container=container, auth_client=auth_client) as client:
            response = APIHelper(client=client).get_calendar(
                reference_date="2026-07-31",
                window="currentAndNextMonths",
            )

        assert response.status_code == codes.UNAUTHORIZED

    async def test_authenticated_principal_reaches_author_scoped_endpoint(
        self,
        container: AsyncContainer,
    ) -> None:
        username = "sdk-authenticated-owner"
        auth_client = FakeAuthenticationClient(username=username, role=RoleEnum.OWNER)
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
        assert response.json() == {
            "referenceDate": "2026-07-31",
            "window": "currentAndNextMonths",
            "summary": {"memorableDateCount": 0, "birthdayCount": 0},
            "entries": [],
        }

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
