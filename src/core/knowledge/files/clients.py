from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from core.knowledge.files.schemas import KnowledgeFileUploadParams, ProcessedKnowledgePhoto


class KnowledgeFileClient(ABC):
    @abstractmethod
    async def upload_file(
        self,
        *,
        content: bytes,
        object_name: str,
        content_type: str,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def stream_file(self, *, object_name: str) -> AsyncIterator[bytes]:
        raise NotImplementedError

    @abstractmethod
    async def init_storage(self) -> None:
        raise NotImplementedError


class KnowledgeFileObjectCleaner(ABC):
    @abstractmethod
    async def cleanup_objects(self, *, object_names: tuple[str, ...]) -> None:
        raise NotImplementedError


class KnowledgeFileRollbackRegistrar(ABC):
    @abstractmethod
    def register_new_object(self, *, object_name: str) -> None:
        raise NotImplementedError


class KnowledgePhotoProcessor(ABC):
    @abstractmethod
    def process(self, *, params: KnowledgeFileUploadParams) -> ProcessedKnowledgePhoto:
        raise NotImplementedError
