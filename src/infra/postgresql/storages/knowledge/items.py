from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.knowledge.exceptions import (
    KnowledgeConflictError,
    KnowledgeItemNotFoundError,
    KnowledgeTagNotFoundError,
)
from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.items.schemas import (
    KnowledgeItem,
    KnowledgeItemCreateParams,
    KnowledgeItemUpdateParams,
    KnowledgeTag,
    KnowledgeTagCreateParams,
)
from core.knowledge.items.storages import KnowledgeItemsStorage
from infra.postgresql.models.knowledge.items import (
    KnowledgeItemModel,
    KnowledgeItemTagModel,
    KnowledgeTagModel,
)


@dataclass(kw_only=True)
class KnowledgeItemsDatabaseStorage(KnowledgeItemsStorage):
    session: AsyncSession

    async def get_item(
        self,
        *,
        item_id: str,
        author_username: str,
        kind: KnowledgeItemKind,
    ) -> KnowledgeItem:
        query = select(KnowledgeItemModel).where(
            KnowledgeItemModel.id == item_id,
            KnowledgeItemModel.author_username == author_username,
            KnowledgeItemModel.kind == kind,
        )
        model = await self.session.scalar(query)
        if model is None:
            raise KnowledgeItemNotFoundError
        tags = await self.load_item_tags(
            item_ids={item_id},
            author_username=author_username,
        )
        return model.to_domain_schema(tags=tags.get(item_id, []))

    async def get_item_for_author(
        self,
        *,
        item_id: str,
        author_username: str,
    ) -> KnowledgeItem:
        query = select(KnowledgeItemModel).where(
            KnowledgeItemModel.id == item_id,
            KnowledgeItemModel.author_username == author_username,
        )
        model = await self.session.scalar(query)
        if model is None:
            raise KnowledgeItemNotFoundError
        tags = await self.load_item_tags(
            item_ids={item_id},
            author_username=author_username,
        )
        return model.to_domain_schema(tags=tags.get(item_id, []))

    async def get_items_by_ids(
        self,
        *,
        item_ids: set[str],
        author_username: str,
        kind: KnowledgeItemKind,
    ) -> list[KnowledgeItem]:
        if not item_ids:
            return []
        query = select(KnowledgeItemModel).where(
            KnowledgeItemModel.id.in_(item_ids),
            KnowledgeItemModel.author_username == author_username,
            KnowledgeItemModel.kind == kind,
        )
        models = list(await self.session.scalars(query))
        tags_by_item_id = await self.load_item_tags(
            item_ids={model.id for model in models},
            author_username=author_username,
        )
        return [model.to_domain_schema(tags=tags_by_item_id.get(model.id, [])) for model in models]

    async def create_item(self, *, params: KnowledgeItemCreateParams) -> KnowledgeItem:
        model = KnowledgeItemModel.from_create_params(params=params)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return model.to_domain_schema(tags=[])

    async def update_item(
        self,
        *,
        item: KnowledgeItem,
        params: KnowledgeItemUpdateParams,
        updated_at: datetime,
    ) -> KnowledgeItem:
        query = (
            update(KnowledgeItemModel)
            .where(
                KnowledgeItemModel.id == item.id,
                KnowledgeItemModel.author_username == item.author_username,
                KnowledgeItemModel.kind == item.kind,
            )
            .values(
                display_name=params.display_name,
                description=params.description,
                updated_at=updated_at,
            )
            .returning(KnowledgeItemModel)
        )
        model = await self.session.scalar(query)
        if model is None:
            raise KnowledgeItemNotFoundError
        return model.to_domain_schema(tags=item.tags)

    async def delete_item(
        self,
        *,
        item_id: str,
        author_username: str,
        kind: KnowledgeItemKind,
    ) -> None:
        query = (
            delete(KnowledgeItemModel)
            .where(
                KnowledgeItemModel.id == item_id,
                KnowledgeItemModel.author_username == author_username,
                KnowledgeItemModel.kind == kind,
            )
            .returning(KnowledgeItemModel.id)
        )
        deleted_id = await self.session.scalar(query)
        if deleted_id is None:
            raise KnowledgeItemNotFoundError

    async def touch_items(
        self,
        *,
        item_ids: set[str],
        author_username: str,
        kind: KnowledgeItemKind,
        updated_at: datetime,
    ) -> None:
        if not item_ids:
            return
        await self.session.execute(
            update(KnowledgeItemModel)
            .where(
                KnowledgeItemModel.id.in_(item_ids),
                KnowledgeItemModel.author_username == author_username,
                KnowledgeItemModel.kind == kind,
            )
            .values(updated_at=updated_at),
        )

    async def replace_item_tags(
        self,
        *,
        item_id: str,
        author_username: str,
        tag_ids: list[str],
    ) -> None:
        await self.session.execute(
            delete(KnowledgeItemTagModel).where(
                KnowledgeItemTagModel.item_id == item_id,
                KnowledgeItemTagModel.author_username == author_username,
            ),
        )
        self.session.add_all(
            [
                KnowledgeItemTagModel(
                    item_id=item_id,
                    tag_id=tag_id,
                    author_username=author_username,
                )
                for tag_id in dict.fromkeys(tag_ids)
            ],
        )
        await self.session.flush()

    async def list_tags(
        self,
        *,
        author_username: str,
        search_query: str | None,
    ) -> list[KnowledgeTag]:
        query = select(KnowledgeTagModel).where(
            KnowledgeTagModel.author_username == author_username,
        )
        if search_query is not None and search_query.strip():
            query = query.where(
                func.lower(KnowledgeTagModel.name).contains(search_query.strip().casefold()),
            )
        query = query.order_by(func.lower(KnowledgeTagModel.name), KnowledgeTagModel.id)
        return [model.to_domain_schema() for model in await self.session.scalars(query)]

    async def get_tag(self, *, tag_id: str, author_username: str) -> KnowledgeTag:
        query = select(KnowledgeTagModel).where(
            KnowledgeTagModel.id == tag_id,
            KnowledgeTagModel.author_username == author_username,
        )
        model = await self.session.scalar(query)
        if model is None:
            raise KnowledgeTagNotFoundError
        return model.to_domain_schema()

    async def get_tags_by_ids(
        self,
        *,
        tag_ids: set[str],
        author_username: str,
    ) -> list[KnowledgeTag]:
        if not tag_ids:
            return []
        query = select(KnowledgeTagModel).where(
            KnowledgeTagModel.id.in_(tag_ids),
            KnowledgeTagModel.author_username == author_username,
        )
        return [model.to_domain_schema() for model in await self.session.scalars(query)]

    async def find_tag_by_name(
        self,
        *,
        name: str,
        author_username: str,
    ) -> KnowledgeTag | None:
        query = select(KnowledgeTagModel).where(
            KnowledgeTagModel.author_username == author_username,
            func.lower(KnowledgeTagModel.name) == name.casefold(),
        )
        model = await self.session.scalar(query)
        return model.to_domain_schema() if model is not None else None

    async def create_tag(self, *, params: KnowledgeTagCreateParams) -> KnowledgeTag:
        model = KnowledgeTagModel.from_create_params(params=params)
        self.session.add(model)
        try:
            await self.session.flush()
        except IntegrityError as error:
            raise KnowledgeConflictError from error
        await self.session.refresh(model)
        return model.to_domain_schema()

    async def update_tag(
        self,
        *,
        tag: KnowledgeTag,
        name: str,
        updated_at: datetime,
    ) -> KnowledgeTag:
        query = (
            update(KnowledgeTagModel)
            .where(
                KnowledgeTagModel.id == tag.id,
                KnowledgeTagModel.author_username == tag.author_username,
            )
            .values(name=name, updated_at=updated_at)
            .returning(KnowledgeTagModel)
        )
        try:
            model = await self.session.scalar(query)
        except IntegrityError as error:
            raise KnowledgeConflictError from error
        if model is None:
            raise KnowledgeTagNotFoundError
        return model.to_domain_schema()

    async def is_tag_used(self, *, tag_id: str, author_username: str) -> bool:
        query = select(KnowledgeItemTagModel.item_id).where(
            KnowledgeItemTagModel.tag_id == tag_id,
            KnowledgeItemTagModel.author_username == author_username,
        )
        return await self.session.scalar(query) is not None

    async def delete_tag(self, *, tag_id: str, author_username: str) -> None:
        query = (
            delete(KnowledgeTagModel)
            .where(
                KnowledgeTagModel.id == tag_id,
                KnowledgeTagModel.author_username == author_username,
            )
            .returning(KnowledgeTagModel.id)
        )
        deleted_id = await self.session.scalar(query)
        if deleted_id is None:
            raise KnowledgeTagNotFoundError

    async def load_item_tags(
        self,
        *,
        item_ids: set[str],
        author_username: str,
    ) -> dict[str, list[KnowledgeTag]]:
        if not item_ids:
            return {}
        query = (
            select(KnowledgeItemTagModel.item_id, KnowledgeTagModel)
            .join(
                KnowledgeTagModel,
                and_(
                    KnowledgeTagModel.id == KnowledgeItemTagModel.tag_id,
                    KnowledgeTagModel.author_username == KnowledgeItemTagModel.author_username,
                ),
            )
            .where(
                KnowledgeItemTagModel.item_id.in_(item_ids),
                KnowledgeItemTagModel.author_username == author_username,
            )
            .order_by(
                KnowledgeItemTagModel.item_id,
                func.lower(KnowledgeTagModel.name),
                KnowledgeTagModel.id,
            )
        )
        tags_by_item_id: dict[str, list[KnowledgeTag]] = {}
        for item_id, model in (await self.session.execute(query)).tuples():
            tags_by_item_id.setdefault(item_id, []).append(model.to_domain_schema())
        return tags_by_item_id
