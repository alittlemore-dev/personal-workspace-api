from dataclasses import dataclass

from sqlalchemy import and_, delete, distinct, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.knowledge.dates.enums import KnowledgeDateListSort
from core.knowledge.dates.schemas import (
    KnowledgeDateDetails,
    KnowledgeDateFilters,
    KnowledgeDatePersonLink,
)
from core.knowledge.dates.storages import KnowledgeDatesStorage
from core.knowledge.exceptions import KnowledgeDateNotFoundError
from core.knowledge.items.enums import KnowledgeItemKind
from infra.postgresql.models.knowledge.dates import (
    KnowledgeDateDetailsModel,
    KnowledgeDatePersonModel,
)
from infra.postgresql.models.knowledge.items import (
    KnowledgeItemModel,
    KnowledgeItemTagModel,
)


@dataclass(kw_only=True)
class KnowledgeDatesDatabaseStorage(KnowledgeDatesStorage):
    session: AsyncSession

    async def list_details_for_months(
        self,
        *,
        months: tuple[int, ...],
        author_username: str,
    ) -> list[KnowledgeDateDetails]:
        query = (
            select(KnowledgeDateDetailsModel)
            .where(
                KnowledgeDateDetailsModel.author_username == author_username,
                KnowledgeDateDetailsModel.month.in_(months),
            )
            .order_by(
                KnowledgeDateDetailsModel.month,
                KnowledgeDateDetailsModel.day,
                KnowledgeDateDetailsModel.item_id,
            )
        )
        return [model.to_domain_schema() for model in await self.session.scalars(query)]

    async def list_date_page(
        self,
        *,
        filters: KnowledgeDateFilters,
    ) -> tuple[list[str], int]:
        conditions = [
            KnowledgeItemModel.author_username == filters.author_username,
            KnowledgeItemModel.kind == KnowledgeItemKind.DATE,
            KnowledgeDateDetailsModel.author_username == filters.author_username,
        ]
        if filters.search_query is not None:
            conditions.append(
                func.lower(KnowledgeItemModel.display_name).contains(
                    filters.search_query.casefold(),
                ),
            )
        if filters.tag_ids:
            tagged_items = (
                select(KnowledgeItemTagModel.item_id)
                .where(
                    KnowledgeItemTagModel.author_username == filters.author_username,
                    KnowledgeItemTagModel.tag_id.in_(filters.tag_ids),
                )
                .group_by(KnowledgeItemTagModel.item_id)
                .having(
                    func.count(distinct(KnowledgeItemTagModel.tag_id)) == len(set(filters.tag_ids)),
                )
            )
            conditions.append(KnowledgeItemModel.id.in_(tagged_items))
        if filters.related_person_id is not None:
            linked_dates = select(KnowledgeDatePersonModel.date_item_id).where(
                KnowledgeDatePersonModel.author_username == filters.author_username,
                KnowledgeDatePersonModel.person_item_id == filters.related_person_id,
            )
            conditions.append(KnowledgeItemModel.id.in_(linked_dates))
        ordering = {
            KnowledgeDateListSort.DATE_ASC: (
                KnowledgeDateDetailsModel.month.asc(),
                KnowledgeDateDetailsModel.day.asc(),
                func.lower(KnowledgeItemModel.display_name).asc(),
                KnowledgeItemModel.id.asc(),
            ),
            KnowledgeDateListSort.DATE_DESC: (
                KnowledgeDateDetailsModel.month.desc(),
                KnowledgeDateDetailsModel.day.desc(),
                func.lower(KnowledgeItemModel.display_name).desc(),
                KnowledgeItemModel.id.desc(),
            ),
            KnowledgeDateListSort.UPDATED_NEWEST: (
                KnowledgeItemModel.updated_at.desc(),
                KnowledgeItemModel.id.desc(),
            ),
            KnowledgeDateListSort.UPDATED_OLDEST: (
                KnowledgeItemModel.updated_at.asc(),
                KnowledgeItemModel.id.asc(),
            ),
            KnowledgeDateListSort.NAME_ASC: (
                func.lower(KnowledgeItemModel.display_name).asc(),
                KnowledgeItemModel.id.asc(),
            ),
            KnowledgeDateListSort.NAME_DESC: (
                func.lower(KnowledgeItemModel.display_name).desc(),
                KnowledgeItemModel.id.desc(),
            ),
        }[filters.sort]
        details_join = and_(
            KnowledgeDateDetailsModel.item_id == KnowledgeItemModel.id,
            KnowledgeDateDetailsModel.author_username == KnowledgeItemModel.author_username,
        )
        page_query = (
            select(KnowledgeItemModel.id)
            .join(KnowledgeDateDetailsModel, details_join)
            .where(*conditions)
            .order_by(*ordering)
            .offset(filters.offset)
            .limit(filters.limit)
        )
        count_query = (
            select(func.count(KnowledgeItemModel.id))
            .join(KnowledgeDateDetailsModel, details_join)
            .where(*conditions)
        )
        item_ids = list(await self.session.scalars(page_query))
        total_count = (await self.session.scalar(count_query)) or 0
        return item_ids, total_count

    async def list_details(
        self,
        *,
        item_ids: list[str],
        author_username: str,
    ) -> list[KnowledgeDateDetails]:
        if not item_ids:
            return []
        query = select(KnowledgeDateDetailsModel).where(
            KnowledgeDateDetailsModel.item_id.in_(item_ids),
            KnowledgeDateDetailsModel.author_username == author_username,
        )
        return [model.to_domain_schema() for model in await self.session.scalars(query)]

    async def get_details(
        self,
        *,
        item_id: str,
        author_username: str,
    ) -> KnowledgeDateDetails:
        query = select(KnowledgeDateDetailsModel).where(
            KnowledgeDateDetailsModel.item_id == item_id,
            KnowledgeDateDetailsModel.author_username == author_username,
        )
        model = await self.session.scalar(query)
        if model is None:
            raise KnowledgeDateNotFoundError
        return model.to_domain_schema()

    async def create_details(
        self,
        *,
        details: KnowledgeDateDetails,
        author_username: str,
    ) -> KnowledgeDateDetails:
        model = KnowledgeDateDetailsModel.from_domain_schema(
            details=details,
            author_username=author_username,
        )
        self.session.add(model)
        await self.session.flush()
        return model.to_domain_schema()

    async def update_details(
        self,
        *,
        details: KnowledgeDateDetails,
        author_username: str,
    ) -> KnowledgeDateDetails:
        query = (
            update(KnowledgeDateDetailsModel)
            .where(
                KnowledgeDateDetailsModel.item_id == details.item_id,
                KnowledgeDateDetailsModel.author_username == author_username,
            )
            .values(
                day=details.date.day,
                month=details.date.month,
                year=details.date.year,
            )
            .returning(KnowledgeDateDetailsModel)
        )
        model = await self.session.scalar(query)
        if model is None:
            raise KnowledgeDateNotFoundError
        return model.to_domain_schema()

    async def list_person_links(
        self,
        *,
        date_ids: set[str],
        author_username: str,
    ) -> list[KnowledgeDatePersonLink]:
        if not date_ids:
            return []
        query = (
            select(KnowledgeDatePersonModel)
            .where(
                KnowledgeDatePersonModel.date_item_id.in_(date_ids),
                KnowledgeDatePersonModel.author_username == author_username,
            )
            .order_by(
                KnowledgeDatePersonModel.date_item_id,
                KnowledgeDatePersonModel.person_item_id,
            )
        )
        return [model.to_domain_schema() for model in await self.session.scalars(query)]

    async def list_date_ids_for_person(
        self,
        *,
        person_id: str,
        author_username: str,
    ) -> list[str]:
        query = (
            select(KnowledgeDatePersonModel.date_item_id)
            .join(
                KnowledgeDateDetailsModel,
                and_(
                    KnowledgeDateDetailsModel.item_id == KnowledgeDatePersonModel.date_item_id,
                    KnowledgeDateDetailsModel.author_username
                    == KnowledgeDatePersonModel.author_username,
                ),
            )
            .where(
                KnowledgeDatePersonModel.person_item_id == person_id,
                KnowledgeDatePersonModel.author_username == author_username,
            )
            .order_by(
                KnowledgeDateDetailsModel.month,
                KnowledgeDateDetailsModel.day,
                KnowledgeDatePersonModel.date_item_id,
            )
        )
        return list(await self.session.scalars(query))

    async def replace_person_links(
        self,
        *,
        date_id: str,
        person_ids: list[str],
        author_username: str,
    ) -> None:
        await self.session.execute(
            delete(KnowledgeDatePersonModel).where(
                KnowledgeDatePersonModel.date_item_id == date_id,
                KnowledgeDatePersonModel.author_username == author_username,
            ),
        )
        self.session.add_all(
            [
                KnowledgeDatePersonModel(
                    date_item_id=date_id,
                    person_item_id=person_id,
                    author_username=author_username,
                )
                for person_id in person_ids
            ],
        )
        await self.session.flush()
