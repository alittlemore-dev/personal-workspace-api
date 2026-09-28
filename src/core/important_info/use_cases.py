from dataclasses import dataclass

from core.important_info.exceptions import InvalidImportantInfoOrderError
from core.important_info.schemas import ImportantInfo
from core.important_info.storages import ImportantInfoStorage


@dataclass(frozen=True, slots=True, kw_only=True)
class ImportantInfoUseCase:
    storage: ImportantInfoStorage

    async def list_items(self, *, author_username: str) -> list[ImportantInfo]:
        return await self.storage.list_items(author_username=author_username)

    async def create_item(self, *, text: str, author_username: str) -> ImportantInfo:
        return await self.storage.create_item(text=text, author_username=author_username)

    async def update_item(self, *, item_id: str, text: str, author_username: str) -> ImportantInfo:
        await self.storage.get_item(item_id=item_id, author_username=author_username)
        return await self.storage.update_item(
            item_id=item_id,
            text=text,
            author_username=author_username,
        )

    async def delete_item(self, *, item_id: str, author_username: str) -> None:
        await self.storage.get_item(item_id=item_id, author_username=author_username)
        await self.storage.delete_item(item_id=item_id, author_username=author_username)

    async def set_order(self, *, ids: list[str], author_username: str) -> list[ImportantInfo]:
        current = await self.storage.list_items(author_username=author_username)
        if len(ids) != len(current) or set(ids) != {item.id for item in current}:
            raise InvalidImportantInfoOrderError
        return await self.storage.set_order(ids=ids, author_username=author_username)
