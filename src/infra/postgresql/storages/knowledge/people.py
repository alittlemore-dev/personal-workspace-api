from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, delete, distinct, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.knowledge.exceptions import (
    KnowledgeConflictError,
    PersonNotFoundError,
    PersonRelationshipTypeNotFoundError,
)
from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.people.enums import (
    PersonListSort,
    PersonRelationshipDirection,
)
from core.knowledge.people.schemas import (
    PersonDetails,
    PersonFilters,
    PersonRelationship,
    PersonRelationshipCreateParams,
    PersonRelationshipType,
    PersonRelationshipTypeCreateParams,
    PersonRelationshipTypeUpdateParams,
    PersonRelationshipUpdateParams,
)
from core.knowledge.people.storages import PeopleStorage
from infra.postgresql.models.knowledge.items import (
    KnowledgeItemModel,
    KnowledgeItemTagModel,
)
from infra.postgresql.models.knowledge.people import (
    PersonDetailsModel,
    PersonRelationshipModel,
    PersonRelationshipTypeModel,
)


@dataclass(kw_only=True)
class PeopleDatabaseStorage(PeopleStorage):
    session: AsyncSession

    async def list_birthday_details_for_months(
        self,
        *,
        months: tuple[int, ...],
        author_username: str,
    ) -> list[PersonDetails]:
        query = (
            select(PersonDetailsModel)
            .where(
                PersonDetailsModel.author_username == author_username,
                PersonDetailsModel.birthday_month.in_(months),
                PersonDetailsModel.birthday_day.is_not(None),
            )
            .order_by(
                PersonDetailsModel.birthday_month,
                PersonDetailsModel.birthday_day,
                PersonDetailsModel.item_id,
            )
        )
        return [model.to_domain_schema() for model in await self.session.scalars(query)]

    async def list_person_page(
        self,
        *,
        filters: PersonFilters,
    ) -> tuple[list[str], int]:
        conditions = [
            KnowledgeItemModel.author_username == filters.author_username,
            KnowledgeItemModel.kind == KnowledgeItemKind.PERSON,
            PersonDetailsModel.author_username == filters.author_username,
        ]
        if filters.search_query is not None and filters.search_query.strip():
            search_query = filters.search_query.strip()
            normalized_search_query = search_query.casefold()
            conditions.append(
                or_(
                    func.lower(PersonDetailsModel.last_name).contains(
                        normalized_search_query,
                    ),
                    func.lower(PersonDetailsModel.first_name).contains(
                        normalized_search_query,
                    ),
                    func.lower(PersonDetailsModel.middle_name).contains(
                        normalized_search_query,
                    ),
                    func.lower(PersonDetailsModel.email).contains(normalized_search_query),
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
        ordering = {
            PersonListSort.UPDATED_NEWEST: (
                KnowledgeItemModel.updated_at.desc(),
                KnowledgeItemModel.id.desc(),
            ),
            PersonListSort.UPDATED_OLDEST: (
                KnowledgeItemModel.updated_at.asc(),
                KnowledgeItemModel.id.asc(),
            ),
            PersonListSort.NAME_ASC: (
                func.lower(KnowledgeItemModel.display_name).asc(),
                KnowledgeItemModel.id.asc(),
            ),
            PersonListSort.NAME_DESC: (
                func.lower(KnowledgeItemModel.display_name).desc(),
                KnowledgeItemModel.id.desc(),
            ),
        }[filters.sort]
        details_join = and_(
            PersonDetailsModel.item_id == KnowledgeItemModel.id,
            PersonDetailsModel.author_username == KnowledgeItemModel.author_username,
        )
        page_query = (
            select(KnowledgeItemModel.id)
            .join(PersonDetailsModel, details_join)
            .where(*conditions)
            .order_by(*ordering)
            .offset(filters.offset)
            .limit(filters.limit)
        )
        count_query = (
            select(func.count(KnowledgeItemModel.id))
            .join(PersonDetailsModel, details_join)
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
    ) -> list[PersonDetails]:
        if not item_ids:
            return []
        query = select(PersonDetailsModel).where(
            PersonDetailsModel.item_id.in_(item_ids),
            PersonDetailsModel.author_username == author_username,
        )
        return [model.to_domain_schema() for model in await self.session.scalars(query)]

    async def get_details(self, *, item_id: str, author_username: str) -> PersonDetails:
        query = select(PersonDetailsModel).where(
            PersonDetailsModel.item_id == item_id,
            PersonDetailsModel.author_username == author_username,
        )
        model = await self.session.scalar(query)
        if model is None:
            raise PersonNotFoundError
        return model.to_domain_schema()

    async def create_details(
        self,
        *,
        details: PersonDetails,
        author_username: str,
    ) -> PersonDetails:
        model = PersonDetailsModel.from_domain_schema(
            details=details,
            author_username=author_username,
        )
        self.session.add(model)
        await self.session.flush()
        return model.to_domain_schema()

    async def update_details(
        self,
        *,
        details: PersonDetails,
        author_username: str,
    ) -> PersonDetails:
        birthday = details.birthday
        query = (
            update(PersonDetailsModel)
            .where(
                PersonDetailsModel.item_id == details.item_id,
                PersonDetailsModel.author_username == author_username,
            )
            .values(
                last_name=details.last_name,
                first_name=details.first_name,
                middle_name=details.middle_name,
                email=details.email,
                phone=details.phone,
                telegram=details.telegram,
                birthday_day=birthday.day if birthday is not None else None,
                birthday_month=birthday.month if birthday is not None else None,
                birthday_year=birthday.year if birthday is not None else None,
            )
            .returning(PersonDetailsModel)
        )
        model = await self.session.scalar(query)
        if model is None:
            raise PersonNotFoundError
        return model.to_domain_schema()

    async def list_relationships(
        self,
        *,
        person_id: str,
        author_username: str,
    ) -> list[PersonRelationship]:
        query = (
            select(PersonRelationshipModel, PersonRelationshipTypeModel)
            .join(
                PersonRelationshipTypeModel,
                and_(
                    PersonRelationshipTypeModel.id == PersonRelationshipModel.relationship_type_id,
                    PersonRelationshipTypeModel.author_username
                    == PersonRelationshipModel.author_username,
                ),
            )
            .where(
                PersonRelationshipModel.author_username == author_username,
                or_(
                    PersonRelationshipModel.source_person_id == person_id,
                    PersonRelationshipModel.target_person_id == person_id,
                ),
            )
            .order_by(PersonRelationshipModel.created_at, PersonRelationshipModel.id)
        )
        return [
            relationship_model.to_domain_schema(
                relationship_type=relationship_type_model.to_domain_schema(),
            )
            for relationship_model, relationship_type_model in (
                await self.session.execute(query)
            ).tuples()
        ]

    async def get_relationships_by_ids(
        self,
        *,
        relationship_ids: set[str],
        author_username: str,
    ) -> list[PersonRelationship]:
        if not relationship_ids:
            return []
        query = (
            select(PersonRelationshipModel, PersonRelationshipTypeModel)
            .join(
                PersonRelationshipTypeModel,
                and_(
                    PersonRelationshipTypeModel.id == PersonRelationshipModel.relationship_type_id,
                    PersonRelationshipTypeModel.author_username
                    == PersonRelationshipModel.author_username,
                ),
            )
            .where(
                PersonRelationshipModel.id.in_(relationship_ids),
                PersonRelationshipModel.author_username == author_username,
            )
        )
        return [
            relationship_model.to_domain_schema(
                relationship_type=relationship_type_model.to_domain_schema(),
            )
            for relationship_model, relationship_type_model in (
                await self.session.execute(query)
            ).tuples()
        ]

    async def list_related_person_ids(
        self,
        *,
        person_id: str,
        author_username: str,
    ) -> set[str]:
        query = select(
            PersonRelationshipModel.source_person_id,
            PersonRelationshipModel.target_person_id,
        ).where(
            PersonRelationshipModel.author_username == author_username,
            or_(
                PersonRelationshipModel.source_person_id == person_id,
                PersonRelationshipModel.target_person_id == person_id,
            ),
        )
        related_ids: set[str] = set()
        for source_person_id, target_person_id in (await self.session.execute(query)).tuples():
            related_ids.add(
                target_person_id if source_person_id == person_id else source_person_id,
            )
        return related_ids

    async def create_relationships(
        self,
        *,
        person_id: str,
        author_username: str,
        values: list[PersonRelationshipCreateParams],
        relationship_types: dict[str, PersonRelationshipType],
        created_at: datetime,
    ) -> None:
        models = []
        for value in values:
            relationship_types[value.relationship_type_id]
            source_person_id = person_id
            target_person_id = value.related_person_id
            if value.direction == PersonRelationshipDirection.REVERSE:
                source_person_id, target_person_id = target_person_id, source_person_id
            models.append(
                PersonRelationshipModel(
                    author_username=author_username,
                    source_person_id=source_person_id,
                    target_person_id=target_person_id,
                    relationship_type_id=value.relationship_type_id,
                    note=value.note,
                    created_at=created_at,
                    updated_at=created_at,
                ),
            )
        self.session.add_all(models)
        try:
            await self.session.flush()
        except IntegrityError as error:
            raise KnowledgeConflictError from error

    async def update_relationships(
        self,
        *,
        person_id: str,
        author_username: str,
        values: list[PersonRelationshipUpdateParams],
        relationship_types: dict[str, PersonRelationshipType],
        updated_at: datetime,
    ) -> None:
        for value in values:
            relationship_types[value.relationship_type_id]
            source_person_id = person_id
            target_person_id = value.related_person_id
            if value.direction == PersonRelationshipDirection.REVERSE:
                source_person_id, target_person_id = target_person_id, source_person_id
            try:
                await self.session.execute(
                    update(PersonRelationshipModel)
                    .where(
                        PersonRelationshipModel.id == value.id,
                        PersonRelationshipModel.author_username == author_username,
                        or_(
                            PersonRelationshipModel.source_person_id == person_id,
                            PersonRelationshipModel.target_person_id == person_id,
                        ),
                    )
                    .values(
                        source_person_id=source_person_id,
                        target_person_id=target_person_id,
                        relationship_type_id=value.relationship_type_id,
                        note=value.note,
                        updated_at=updated_at,
                    ),
                )
            except IntegrityError as error:
                raise KnowledgeConflictError from error

    async def delete_relationships(
        self,
        *,
        relationship_ids: set[str],
        author_username: str,
    ) -> None:
        if not relationship_ids:
            return
        await self.session.execute(
            delete(PersonRelationshipModel).where(
                PersonRelationshipModel.id.in_(relationship_ids),
                PersonRelationshipModel.author_username == author_username,
            ),
        )

    async def list_relationship_types(
        self,
        *,
        author_username: str,
    ) -> list[PersonRelationshipType]:
        query = (
            select(PersonRelationshipTypeModel)
            .where(PersonRelationshipTypeModel.author_username == author_username)
            .order_by(
                func.lower(PersonRelationshipTypeModel.forward_name),
                PersonRelationshipTypeModel.id,
            )
        )
        return [model.to_domain_schema() for model in await self.session.scalars(query)]

    async def get_relationship_type(
        self,
        *,
        relationship_type_id: str,
        author_username: str,
    ) -> PersonRelationshipType:
        query = select(PersonRelationshipTypeModel).where(
            PersonRelationshipTypeModel.id == relationship_type_id,
            PersonRelationshipTypeModel.author_username == author_username,
        )
        model = await self.session.scalar(query)
        if model is None:
            raise PersonRelationshipTypeNotFoundError
        return model.to_domain_schema()

    async def get_relationship_types_by_ids(
        self,
        *,
        relationship_type_ids: set[str],
        author_username: str,
    ) -> list[PersonRelationshipType]:
        if not relationship_type_ids:
            return []
        query = select(PersonRelationshipTypeModel).where(
            PersonRelationshipTypeModel.id.in_(relationship_type_ids),
            PersonRelationshipTypeModel.author_username == author_username,
        )
        return [model.to_domain_schema() for model in await self.session.scalars(query)]

    async def create_relationship_type(
        self,
        *,
        params: PersonRelationshipTypeCreateParams,
    ) -> PersonRelationshipType:
        model = PersonRelationshipTypeModel.from_create_params(params=params)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return model.to_domain_schema()

    async def update_relationship_type(
        self,
        *,
        relationship_type: PersonRelationshipType,
        params: PersonRelationshipTypeUpdateParams,
        updated_at: datetime,
    ) -> PersonRelationshipType:
        query = (
            update(PersonRelationshipTypeModel)
            .where(
                PersonRelationshipTypeModel.id == relationship_type.id,
                PersonRelationshipTypeModel.author_username == relationship_type.author_username,
            )
            .values(
                is_symmetric=params.is_symmetric,
                forward_name=params.forward_name,
                reverse_name=params.reverse_name,
                updated_at=updated_at,
            )
            .returning(PersonRelationshipTypeModel)
        )
        model = await self.session.scalar(query)
        if model is None:
            raise PersonRelationshipTypeNotFoundError
        return model.to_domain_schema()

    async def is_relationship_type_used(
        self,
        *,
        relationship_type_id: str,
        author_username: str,
    ) -> bool:
        query = select(PersonRelationshipModel.id).where(
            PersonRelationshipModel.relationship_type_id == relationship_type_id,
            PersonRelationshipModel.author_username == author_username,
        )
        return await self.session.scalar(query) is not None

    async def delete_relationship_type(
        self,
        *,
        relationship_type_id: str,
        author_username: str,
    ) -> None:
        query = (
            delete(PersonRelationshipTypeModel)
            .where(
                PersonRelationshipTypeModel.id == relationship_type_id,
                PersonRelationshipTypeModel.author_username == author_username,
            )
            .returning(PersonRelationshipTypeModel.id)
        )
        deleted_id = await self.session.scalar(query)
        if deleted_id is None:
            raise PersonRelationshipTypeNotFoundError
