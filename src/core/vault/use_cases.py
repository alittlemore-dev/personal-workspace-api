from dataclasses import dataclass

from core.vault.schemas import GetVaultStatisticsParams, VaultConfig, VaultEntry, VaultStatistics
from core.vault.storages import VaultStorage


@dataclass(frozen=True, slots=True, kw_only=True)
class VaultUseCase:
    storage: VaultStorage
    config: VaultConfig

    async def list_recent(self, *, author_username: str) -> list[VaultEntry]:
        return await self.storage.list_recent(
            author_username=author_username,
            limit=self.config.recent_limit,
        )

    async def get_statistics(self, *, params: GetVaultStatisticsParams) -> VaultStatistics:
        values = await self.storage.list_statistics(
            author_username=params.author_username,
            from_datetime=params.current_datetime - self.config.activity_period,
            to_datetime=params.current_datetime,
        )
        return VaultStatistics.from_kind_statistics(values=values)
