from abc import ABC, abstractmethod
from datetime import datetime

from core.vault.schemas import VaultEntry, VaultKindStatistics


class VaultStorage(ABC):
    @abstractmethod
    async def list_recent(self, *, author_username: str, limit: int) -> list[VaultEntry]: ...

    @abstractmethod
    async def list_statistics(
        self,
        *,
        author_username: str,
        from_datetime: datetime,
        to_datetime: datetime,
    ) -> list[VaultKindStatistics]: ...
