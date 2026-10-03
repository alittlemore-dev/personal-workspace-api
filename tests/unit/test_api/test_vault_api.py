from datetime import UTC, datetime
from unittest.mock import Mock

import pytest_asyncio

from core.vault.schemas import VaultEntry, VaultStatistics
from core.vault.use_cases import VaultUseCase
from tests.test_cases import ApiTestCase
from tests.unit.conftest import TEST_USERNAME


class TestVaultApi(ApiTestCase):
    @pytest_asyncio.fixture(autouse=True)
    async def setup(self) -> None:
        self.use_case: Mock = await self.container.container.get(VaultUseCase)

    def test_recent_maps_only_the_authenticated_author(self) -> None:
        self.use_case.list_recent.return_value = [
            VaultEntry(
                id="a" * 32,
                source="resume",
                kind="resume",
                display_name="CV",
                updated_at=datetime(2026, 9, 1, tzinfo=UTC),
            ),
        ]
        response = self.api.client.get("/api/vault/recent")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["items"][0]["displayName"] == "CV"
        assert response.json()["items"][0]["source"] == "resume"
        self.use_case.list_recent.assert_awaited_once_with(author_username=TEST_USERNAME)

    def test_statistics_maps_zero_counts_and_current_author(self) -> None:
        self.use_case.get_statistics.return_value = VaultStatistics.from_kind_statistics(values=[])
        response = self.api.client.get("/api/vault/statistics")
        assert response.status_code == 200
        assert response.json() == {
            "totalCount": 0,
            "knowledgeCount": 0,
            "resumeCount": 0,
            "byKind": [],
            "createdLast30DaysCount": 0,
            "createdOrUpdatedLast30DaysCount": 0,
        }
        params = self.use_case.get_statistics.await_args.kwargs["params"]
        assert params.author_username == TEST_USERNAME
        assert params.current_datetime.tzinfo == UTC
