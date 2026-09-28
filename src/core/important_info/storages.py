from abc import ABC, abstractmethod

from core.important_info.schemas import ImportantInfo


class ImportantInfoStorage(ABC):
    @abstractmethod
    async def list_items(self, *, author_username: str) -> list[ImportantInfo]:
        raise NotImplementedError

    @abstractmethod
    async def get_item(self, *, item_id: str, author_username: str) -> ImportantInfo:
        raise NotImplementedError

    @abstractmethod
    async def create_item(self, *, text: str, author_username: str) -> ImportantInfo:
        raise NotImplementedError

    @abstractmethod
    async def update_item(self, *, item_id: str, text: str, author_username: str) -> ImportantInfo:
        raise NotImplementedError

    @abstractmethod
    async def delete_item(self, *, item_id: str, author_username: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def set_order(self, *, ids: list[str], author_username: str) -> list[ImportantInfo]:
        raise NotImplementedError
