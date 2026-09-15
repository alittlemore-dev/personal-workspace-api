import uuid
from collections.abc import AsyncGenerator, Generator, Sequence
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from dishka import AsyncContainer, make_async_container
from dishka.integrations.litestar import LitestarProvider, setup_dishka
from litestar import Litestar
from litestar.testing import TestClient
from litestar.types import Middleware

from entrypoints.litestar.initializers.main import create_litestar_app
from infra.ioc.prodivers.auth_provider import AuthProvider
from infra.ioc.prodivers.database_provider import DatabaseProvider
from tests.unit.mocks.providers.cache_tools import MockCacheToolsProvider
from tests.unit.mocks.providers.calendar import MockCalendarProvider
from tests.unit.mocks.providers.files import MockFilesProvider
from tests.unit.mocks.providers.general import MockGeneralProvider
from tests.unit.mocks.providers.healthcheck import MockHealthcheckProvider
from tests.unit.mocks.providers.knowledge import MockKnowledgeProvider
from tests.unit.mocks.providers.resumes import MockResumesProvider
from tests.unit.mocks.providers.wiki_links import MockWikiLinksProvider

TEST_CURRENT_DATETIME = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
TEST_OWNER_USERNAME = "test-owner"


@pytest.fixture
def random_suffix(global_random_uuid: uuid.UUID) -> str:
    return global_random_uuid.hex[:8]


@pytest_asyncio.fixture(loop_scope="function")
async def container(
    global_random_uuid: uuid.UUID,
    global_random_hex_uuid: str,
    random_suffix: str,
) -> AsyncGenerator[AsyncContainer]:
    container = make_async_container(
        LitestarProvider(),
        DatabaseProvider(),
        AuthProvider(),
        MockGeneralProvider(
            uuid_=global_random_uuid,
            hex_uuid=global_random_hex_uuid,
            current_datetime=TEST_CURRENT_DATETIME,
        ),
        MockFilesProvider(random_suffix=random_suffix),
        MockCalendarProvider(),
        MockKnowledgeProvider(),
        MockResumesProvider(),
        MockCacheToolsProvider(),
        MockWikiLinksProvider(),
        MockHealthcheckProvider(),
    )
    yield container
    await container.close()


@pytest.fixture
def app(container: AsyncContainer) -> Litestar:
    return build_test_app(container=container, extra_middlewares=[])


def build_test_app(
    *,
    container: AsyncContainer,
    extra_middlewares: Sequence[Middleware],
) -> Litestar:
    test_app = create_litestar_app(
        lifespan=[],
        container=container,
        extra_plugins=[],
        extra_middlewares=extra_middlewares,
    )
    setup_dishka(container=container, app=test_app)
    return test_app


@pytest.fixture
def client(app: Litestar) -> Generator[TestClient]:
    with TestClient(app) as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": TEST_OWNER_USERNAME, "password": "test-owner-password"},
        )
        assert login_response.status_code == 200
        session_response = client.get("/api/auth/session")
        assert session_response.status_code == 200
        csrf_token = client.cookies["XSRF-TOKEN"]
        client.headers["X-XSRF-TOKEN"] = csrf_token
        yield client
