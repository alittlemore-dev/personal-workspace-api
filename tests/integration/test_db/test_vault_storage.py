import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy import delete, update

from core.knowledge.items.enums import KnowledgeItemKind
from core.vault.schemas import GetVaultStatisticsParams, VaultConfig
from core.vault.use_cases import VaultUseCase
from infra.config.settings import Settings
from infra.postgresql.models import KnowledgeItemModel, ResumeModel
from infra.postgresql.storages.vault import VaultDatabaseStorage
from tests.test_cases import StorageTestCase

NOW = datetime(2026, 10, 3, tzinfo=UTC)


class TestVaultStorage(StorageTestCase):
    async def test_additional_concrete_source_is_discovered(self, test_settings: Settings) -> None:
        # A separate process prevents a test mapper from leaking into other storage tests.
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "tests.helpers.vault_source_probe",
            env={**os.environ, "DB_NAME": test_settings.database.name},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        assert process.returncode == 0, stderr.decode()

    @pytest_asyncio.fixture(autouse=True)
    async def setup(self) -> None:
        self.storage = VaultDatabaseStorage(session=self.db_session)
        self.use_case = VaultUseCase(
            storage=self.storage,
            config=VaultConfig(recent_limit=8, activity_period=timedelta(days=30)),
        )

    async def add_knowledge(
        self,
        *,
        identifier: int,
        created_at: datetime,
        updated_at: datetime,
        author: str = "owner",
        kind: KnowledgeItemKind = KnowledgeItemKind.PERSON,
    ) -> None:
        self.db_session.add(
            KnowledgeItemModel(
                id=self.factory.core.hex_id(identifier),
                kind=kind,
                author_username=author,
                display_name=f"Entry {identifier}",
                description="notes",
                created_at=created_at,
                updated_at=updated_at,
            ),
        )
        await self.db_session.flush()

    async def add_resume(
        self,
        *,
        identifier: int,
        updated_at: datetime,
        author: str = "owner",
    ) -> None:
        resume = self.factory.core.resume(
            resume_id=identifier,
            author_username=author,
            created_at=updated_at.isoformat(),
            updated_at=updated_at.isoformat(),
        )
        self.db_session.add(ResumeModel.from_domain_schema(resume=resume))
        await self.db_session.flush()

    async def test_recent_global_limit_and_author_isolation(self) -> None:
        for identifier in range(1, 13):
            await self.add_knowledge(
                identifier=identifier,
                created_at=NOW,
                updated_at=NOW + timedelta(minutes=identifier),
            )
            await self.add_resume(
                identifier=identifier,
                updated_at=NOW + timedelta(minutes=identifier, seconds=30),
            )
        await self.add_resume(identifier=99, updated_at=NOW + timedelta(days=1), author="other")
        items = await self.storage.list_recent(author_username="owner", limit=8)
        assert [(item.source, item.id) for item in items] == [
            (source, self.factory.core.hex_id(identifier))
            for identifier in (12, 11, 10, 9)
            for source in ("resume", "knowledge")
        ]
        assert items[0].display_name == "Backend resume"
        await self.db_session.execute(
            delete(ResumeModel).where(ResumeModel.id == self.factory.core.hex_id(12)),
        )
        items = await self.storage.list_recent(author_username="owner", limit=8)
        assert items[0].source == "knowledge"
        assert len(items) == 8

    async def test_recent_stable_order_for_equal_timestamps(self) -> None:
        for identifier in (1, 2):
            await self.add_knowledge(identifier=identifier, created_at=NOW, updated_at=NOW)
            await self.add_resume(identifier=identifier, updated_at=NOW)
        assert [
            (entry.source, entry.id)
            for entry in await self.storage.list_recent(author_username="owner", limit=8)
        ] == [
            (source, self.factory.core.hex_id(identifier))
            for source in ("knowledge", "resume")
            for identifier in (2, 1)
        ]

    async def test_exact_statistics_and_activity_boundaries(self) -> None:
        cutoff = NOW - timedelta(days=30)
        await self.add_knowledge(identifier=1, created_at=cutoff, updated_at=cutoff)
        await self.add_knowledge(
            identifier=2,
            created_at=cutoff - timedelta(microseconds=1),
            updated_at=NOW,
            kind=KnowledgeItemKind.DATE,
        )
        await self.add_knowledge(
            identifier=3,
            created_at=cutoff - timedelta(days=1),
            updated_at=cutoff - timedelta(microseconds=1),
        )
        await self.add_resume(identifier=4, updated_at=NOW)
        await self.add_resume(identifier=5, updated_at=NOW, author="other")
        await self.db_session.execute(
            update(KnowledgeItemModel)
            .where(KnowledgeItemModel.id == self.factory.core.hex_id(2))
            .values(updated_at=NOW),
        )
        statistics = await self.use_case.get_statistics(
            params=GetVaultStatisticsParams(author_username="owner", current_datetime=NOW),
        )
        assert (statistics.total_count, statistics.knowledge_count, statistics.resume_count) == (
            4,
            3,
            1,
        )
        assert statistics.created_last_30_days_count == 2
        assert statistics.created_or_updated_last_30_days_count == 3
        assert {value.kind: value.total_count for value in statistics.by_kind} == {
            "person": 2,
            "date": 1,
            "resume": 1,
        }
        empty = await self.use_case.get_statistics(
            params=GetVaultStatisticsParams(author_username="empty", current_datetime=NOW),
        )
        assert (
            empty.total_count
            == empty.created_last_30_days_count
            == empty.created_or_updated_last_30_days_count
            == 0
        )

    async def test_statistics_excludes_future_activity_and_includes_created_records(self) -> None:
        future = NOW + timedelta(microseconds=1)
        await self.add_knowledge(identifier=1, created_at=future, updated_at=future)
        await self.add_knowledge(identifier=2, created_at=NOW, updated_at=future)
        statistics = await self.use_case.get_statistics(
            params=GetVaultStatisticsParams(
                author_username="owner",
                current_datetime=NOW,
            ),
        )
        assert statistics.total_count == 2
        assert statistics.created_last_30_days_count == 1
        assert statistics.created_or_updated_last_30_days_count == 1
