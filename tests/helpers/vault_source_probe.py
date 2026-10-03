import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import registry

from infra.config.settings import settings

with patch.object(registry, "configure"):
    from infra.postgresql.models import BaseModel, VaultEntryModel

    class AdditionalVaultModel(VaultEntryModel, BaseModel):
        __tablename__ = "test_additional_vault_source"
        __mapper_args__ = {"polymorphic_identity": "additional", "concrete": True}


from infra.postgresql.storages.vault import VaultDatabaseStorage


async def probe() -> None:
    BaseModel.registry.configure()
    engine = create_async_engine(settings.database.url.get_secret_value())
    table = AdditionalVaultModel.__table__
    assert isinstance(table, Table)
    now = datetime.now(UTC)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(table.create)
        async with AsyncSession(engine) as session:
            session.add(
                AdditionalVaultModel(
                    id="a" * 32,
                    author_username="probe",
                    display_name="Additional entry",
                    created_at=now,
                    updated_at=now,
                ),
            )
            await session.flush()
            storage = VaultDatabaseStorage(session=session)
            recent = await storage.list_recent(author_username="probe", limit=8)
            assert [(item.source, item.kind, item.display_name) for item in recent] == [
                ("additional", "additional", "Additional entry"),
            ]
            counts = await storage.list_statistics(
                author_username="probe",
                from_datetime=now - timedelta(days=30),
                to_datetime=now,
            )
            assert [(item.source, item.total_count) for item in counts] == [("additional", 1)]
            assert await storage.list_recent(author_username="other", limit=8) == []
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(table.drop, checkfirst=True)
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(probe())
