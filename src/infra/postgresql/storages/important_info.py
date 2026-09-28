from dataclasses import dataclass

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.important_info.exceptions import ImportantInfoNotFoundError
from core.important_info.schemas import ImportantInfo
from core.important_info.storages import ImportantInfoStorage
from infra.postgresql.models.important_info import ImportantInfoModel


@dataclass(kw_only=True)
class ImportantInfoDatabaseStorage(ImportantInfoStorage):
    session: AsyncSession

    async def list_items(self, *, author_username: str) -> list[ImportantInfo]:
        query = (
            select(ImportantInfoModel)
            .where(ImportantInfoModel.author_username == author_username)
            .order_by(ImportantInfoModel.position, ImportantInfoModel.id)
        )
        return [model.to_domain_schema() for model in await self.session.scalars(query)]

    async def get_item(self, *, item_id: str, author_username: str) -> ImportantInfo:
        query = select(ImportantInfoModel).where(
            ImportantInfoModel.id == item_id,
            ImportantInfoModel.author_username == author_username,
        )
        model = await self.session.scalar(query)
        if model is None:
            raise ImportantInfoNotFoundError
        return model.to_domain_schema()

    async def create_item(self, *, text: str, author_username: str) -> ImportantInfo:
        max_position = await self.session.scalar(
            select(func.max(ImportantInfoModel.position)).where(
                ImportantInfoModel.author_username == author_username,
            ),
        )
        model = ImportantInfoModel(
            text=text,
            author_username=author_username,
            position=(max_position if max_position is not None else -1) + 1,
        )
        self.session.add(model)
        await self.session.flush()
        return model.to_domain_schema()

    async def update_item(self, *, item_id: str, text: str, author_username: str) -> ImportantInfo:
        query = (
            update(ImportantInfoModel)
            .where(
                ImportantInfoModel.id == item_id,
                ImportantInfoModel.author_username == author_username,
            )
            .values(text=text)
            .returning(ImportantInfoModel)
        )
        model = await self.session.scalar(query)
        if model is None:
            raise ImportantInfoNotFoundError
        return model.to_domain_schema()

    async def delete_item(self, *, item_id: str, author_username: str) -> None:
        query = (
            delete(ImportantInfoModel)
            .where(
                ImportantInfoModel.id == item_id,
                ImportantInfoModel.author_username == author_username,
            )
            .returning(ImportantInfoModel.id)
        )
        if await self.session.scalar(query) is None:
            raise ImportantInfoNotFoundError

    async def set_order(self, *, ids: list[str], author_username: str) -> list[ImportantInfo]:
        for position, item_id in enumerate(ids):
            await self.session.execute(
                update(ImportantInfoModel)
                .where(
                    ImportantInfoModel.id == item_id,
                    ImportantInfoModel.author_username == author_username,
                )
                .values(position=position),
            )
        return await self.list_items(author_username=author_username)
