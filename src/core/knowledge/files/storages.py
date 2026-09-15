from abc import ABC, abstractmethod
from datetime import datetime

from core.knowledge.files.schemas import KnowledgeFile


class KnowledgeFilesStorage(ABC):
    @abstractmethod
    async def list_item_files(
        self,
        *,
        item_id: str,
        author_username: str,
    ) -> list[KnowledgeFile]:
        raise NotImplementedError

    @abstractmethod
    async def list_files_for_items(
        self,
        *,
        item_ids: set[str],
        author_username: str,
    ) -> list[KnowledgeFile]:
        raise NotImplementedError

    @abstractmethod
    async def get_file(self, *, file_id: str, author_username: str) -> KnowledgeFile:
        raise NotImplementedError

    @abstractmethod
    async def create_file(self, *, file: KnowledgeFile) -> KnowledgeFile:
        raise NotImplementedError

    @abstractmethod
    async def update_file_name(
        self,
        *,
        file: KnowledgeFile,
        name: str,
        updated_at: datetime,
    ) -> KnowledgeFile:
        raise NotImplementedError

    @abstractmethod
    async def delete_file(self, *, file: KnowledgeFile) -> None:
        raise NotImplementedError
