from dataclasses import dataclass

from core.important_info.exceptions import InvalidImportantInfoOrderError
from core.important_info.schemas import (
    CreateImportantInfoParams,
    ImportantInfo,
    ImportantInfoTargetParams,
    SetImportantInfoOrderParams,
    UpdateImportantInfoParams,
)
from core.important_info.storages import ImportantInfoStorage


@dataclass(frozen=True, slots=True, kw_only=True)
class ImportantInfoUseCase:
    storage: ImportantInfoStorage

    async def list_items(self, *, author_username: str) -> list[ImportantInfo]:
        return await self.storage.list_items(author_username=author_username)

    async def create_item(self, *, params: CreateImportantInfoParams) -> ImportantInfo:
        return await self.storage.create_item(
            text=params.text,
            author_username=params.author_username,
        )

    async def update_item(self, *, params: UpdateImportantInfoParams) -> ImportantInfo:
        await self.storage.get_item(item_id=params.item_id, author_username=params.author_username)
        return await self.storage.update_item(
            item_id=params.item_id,
            text=params.text,
            author_username=params.author_username,
        )

    async def delete_item(self, *, params: ImportantInfoTargetParams) -> None:
        await self.storage.get_item(item_id=params.item_id, author_username=params.author_username)
        await self.storage.delete_item(
            item_id=params.item_id,
            author_username=params.author_username,
        )

    async def set_order(self, *, params: SetImportantInfoOrderParams) -> list[ImportantInfo]:
        current = await self.storage.list_items(author_username=params.author_username)
        if len(params.ids) != len(current) or set(params.ids) != {item.id for item in current}:
            raise InvalidImportantInfoOrderError
        return await self.storage.set_order(ids=params.ids, author_username=params.author_username)
