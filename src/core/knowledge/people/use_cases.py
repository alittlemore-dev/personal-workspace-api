from dataclasses import dataclass, replace
from datetime import datetime

from core.knowledge.dates.schemas import KnowledgeDateReference
from core.knowledge.dates.storages import KnowledgeDatesStorage
from core.knowledge.exceptions import (
    InvalidKnowledgeDataError,
    KnowledgeConflictError,
    KnowledgeTagNotFoundError,
    PersonRelationshipNotFoundError,
    PersonRelationshipTypeNotFoundError,
)
from core.knowledge.files.enums import KnowledgeFileKind
from core.knowledge.files.services import KnowledgeFileCrudService
from core.knowledge.files.storages import KnowledgeFilesStorage
from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.items.schemas import (
    KnowledgeItemCreateParams,
    KnowledgeItemUpdateParams,
)
from core.knowledge.items.services import KnowledgeItemCrudService
from core.knowledge.items.storages import KnowledgeItemsStorage
from core.knowledge.people.schemas import (
    PeoplePage,
    Person,
    PersonFilters,
    PersonQuickCreateParams,
    PersonRelationship,
    PersonRelationshipChanges,
    PersonRelationshipType,
    PersonRelationshipTypeCreateParams,
    PersonRelationshipTypeUpdateParams,
    PersonRelationshipView,
    PersonSummary,
    PersonUpdateParams,
)
from core.knowledge.people.storages import PeopleStorage


@dataclass(kw_only=True, slots=True, frozen=True)
class PeopleUseCase:
    item_service: KnowledgeItemCrudService
    item_storage: KnowledgeItemsStorage
    people_storage: PeopleStorage
    dates_storage: KnowledgeDatesStorage
    file_storage: KnowledgeFilesStorage
    file_service: KnowledgeFileCrudService

    async def list_people(self, *, filters: PersonFilters) -> PeoplePage:
        search_query = (
            filters.search_query.strip()
            if filters.search_query is not None and filters.search_query.strip()
            else None
        )
        effective_filters = replace(filters, search_query=search_query)
        if effective_filters.tag_ids:
            tags = await self.item_storage.get_tags_by_ids(
                tag_ids=set(effective_filters.tag_ids),
                author_username=effective_filters.author_username,
            )
            if len(tags) != len(set(effective_filters.tag_ids)):
                raise KnowledgeTagNotFoundError
        page_item_ids, total_count = await self.people_storage.list_person_page(
            filters=effective_filters,
        )
        unordered_items = await self.item_storage.get_items_by_ids(
            item_ids=set(page_item_ids),
            author_username=effective_filters.author_username,
            kind=KnowledgeItemKind.PERSON,
        )
        items_by_id = {item.id: item for item in unordered_items}
        items = [items_by_id[item_id] for item_id in page_item_ids]
        details = await self.people_storage.list_details(
            item_ids=[item.id for item in items],
            author_username=effective_filters.author_username,
        )
        details_by_id = {value.item_id: value for value in details}
        files = await self.file_storage.list_files_for_items(
            item_ids={item.id for item in items},
            author_username=effective_filters.author_username,
        )
        photos_by_item_id = {
            file.item_id: file for file in files if file.kind == KnowledgeFileKind.PERSON_PHOTO
        }
        return PeoplePage.from_values(
            values=[
                PersonSummary(
                    id=item.id,
                    display_name=item.display_name,
                    email=details_by_id[item.id].email,
                    phone=details_by_id[item.id].phone,
                    telegram=details_by_id[item.id].telegram,
                    birthday=details_by_id[item.id].birthday,
                    tags=item.tags,
                    photo=photos_by_item_id.get(item.id),
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                )
                for item in items
            ],
            total_count=total_count,
            page_size=effective_filters.page_size,
        )

    async def get_person(self, *, person_id: str, author_username: str) -> Person:
        item = await self.item_service.get_item(
            item_id=person_id,
            author_username=author_username,
            kind=KnowledgeItemKind.PERSON,
        )
        details = await self.people_storage.get_details(
            item_id=person_id,
            author_username=author_username,
        )
        relationships = await self.people_storage.list_relationships(
            person_id=person_id,
            author_username=author_username,
        )
        related_ids = {
            relationship.related_person_id_for(person_id=person_id)
            for relationship in relationships
        }
        related_items = await self.item_storage.get_items_by_ids(
            item_ids=related_ids,
            author_username=author_username,
            kind=KnowledgeItemKind.PERSON,
        )
        display_names = {related.id: related.display_name for related in related_items}
        related_dates = await self.list_related_dates(
            person_id=person_id,
            author_username=author_username,
        )
        files = await self.file_storage.list_item_files(
            item_id=person_id,
            author_username=author_username,
        )
        return Person(
            item=item,
            details=details,
            relationships=[
                PersonRelationshipView(
                    id=relationship.id,
                    related_person_id=relationship.related_person_id_for(person_id=person_id),
                    related_person_display_name=display_names[
                        relationship.related_person_id_for(person_id=person_id)
                    ],
                    relationship_type=relationship.relationship_type,
                    direction=relationship.direction_for(person_id=person_id),
                    label=relationship.label_for(person_id=person_id),
                    note=relationship.note,
                    created_at=relationship.created_at,
                    updated_at=relationship.updated_at,
                )
                for relationship in relationships
            ],
            related_dates=related_dates,
            photo=next(
                (file for file in files if file.kind == KnowledgeFileKind.PERSON_PHOTO),
                None,
            ),
            attachments=[file for file in files if file.kind == KnowledgeFileKind.ATTACHMENT],
        )

    async def list_related_dates(
        self,
        *,
        person_id: str,
        author_username: str,
    ) -> list[KnowledgeDateReference]:
        date_ids = await self.dates_storage.list_date_ids_for_person(
            person_id=person_id,
            author_username=author_username,
        )
        if not date_ids:
            return []
        items = await self.item_storage.get_items_by_ids(
            item_ids=set(date_ids),
            author_username=author_username,
            kind=KnowledgeItemKind.DATE,
        )
        details = await self.dates_storage.list_details(
            item_ids=date_ids,
            author_username=author_username,
        )
        items_by_id = {item.id: item for item in items}
        details_by_id = {value.item_id: value for value in details}
        return sorted(
            [
                KnowledgeDateReference(
                    id=date_id,
                    display_name=items_by_id[date_id].display_name,
                    date=details_by_id[date_id].date,
                )
                for date_id in date_ids
            ],
            key=lambda value: (
                value.date.month,
                value.date.day,
                value.display_name.casefold(),
                value.id,
            ),
        )

    async def create_person(self, *, params: PersonQuickCreateParams) -> Person:
        provisional_details = params.to_details(item_id="")
        item = await self.item_service.create_item(
            params=KnowledgeItemCreateParams(
                kind=KnowledgeItemKind.PERSON,
                author_username=params.author_username,
                display_name=provisional_details.display_name,
                description="",
            ),
        )
        await self.people_storage.create_details(
            details=params.to_details(item_id=item.id),
            author_username=params.author_username,
        )
        return await self.get_person(
            person_id=item.id,
            author_username=params.author_username,
        )

    async def update_person(
        self,
        *,
        person_id: str,
        params: PersonUpdateParams,
        author_username: str,
        current_datetime: datetime,
    ) -> Person:
        item = await self.item_service.get_item(
            item_id=person_id,
            author_username=author_username,
            kind=KnowledgeItemKind.PERSON,
        )
        details = params.to_details(item_id=person_id)
        if details.birthday is not None:
            details.birthday.validate(today=current_datetime.date())
        await self.people_storage.get_details(
            item_id=person_id,
            author_username=author_username,
        )
        mutated_existing_relationships = await self.validate_relationship_changes(
            person_id=person_id,
            changes=params.relationship_changes,
            author_username=author_username,
        )
        await self.item_service.update_item(
            item=item,
            params=KnowledgeItemUpdateParams(
                display_name=details.display_name,
                description=params.description,
            ),
            tag_ids=params.tag_ids,
            updated_at=current_datetime,
        )
        await self.people_storage.update_details(
            details=details,
            author_username=author_username,
        )
        relationship_types = await self.people_storage.get_relationship_types_by_ids(
            relationship_type_ids=(
                {value.relationship_type_id for value in params.relationship_changes.create}
                | {value.relationship_type_id for value in params.relationship_changes.update}
            ),
            author_username=author_username,
        )
        relationship_types_by_id = {value.id: value for value in relationship_types}
        await self.people_storage.create_relationships(
            person_id=person_id,
            author_username=author_username,
            values=params.relationship_changes.create,
            relationship_types=relationship_types_by_id,
            created_at=current_datetime,
        )
        await self.people_storage.update_relationships(
            person_id=person_id,
            author_username=author_username,
            values=params.relationship_changes.update,
            relationship_types=relationship_types_by_id,
            updated_at=current_datetime,
        )
        await self.people_storage.delete_relationships(
            relationship_ids=set(params.relationship_changes.delete_ids),
            author_username=author_username,
        )
        touched_ids = {value.related_person_id for value in params.relationship_changes.create} | {
            value.related_person_id for value in params.relationship_changes.update
        }
        touched_ids.update(
            relationship.related_person_id_for(person_id=person_id)
            for relationship in mutated_existing_relationships
        )
        await self.item_storage.touch_items(
            item_ids=touched_ids,
            author_username=author_username,
            kind=KnowledgeItemKind.PERSON,
            updated_at=current_datetime,
        )
        return await self.get_person(person_id=person_id, author_username=author_username)

    async def validate_relationship_changes(
        self,
        *,
        person_id: str,
        changes: PersonRelationshipChanges,
        author_username: str,
    ) -> list[PersonRelationship]:
        mutation_ids = {value.id for value in changes.update} | set(changes.delete_ids)
        existing_relationships = await self.people_storage.get_relationships_by_ids(
            relationship_ids=mutation_ids,
            author_username=author_username,
        )
        if len(existing_relationships) != len(mutation_ids):
            raise PersonRelationshipNotFoundError
        if any(
            person_id
            not in {
                relationship.source_person_id,
                relationship.target_person_id,
            }
            for relationship in existing_relationships
        ):
            raise PersonRelationshipNotFoundError
        related_ids = {value.related_person_id for value in changes.create} | {
            value.related_person_id for value in changes.update
        }
        if person_id in related_ids:
            raise InvalidKnowledgeDataError
        related_items = await self.item_storage.get_items_by_ids(
            item_ids=related_ids,
            author_username=author_username,
            kind=KnowledgeItemKind.PERSON,
        )
        if len(related_items) != len(related_ids):
            raise PersonRelationshipNotFoundError
        relationship_type_ids = {value.relationship_type_id for value in changes.create} | {
            value.relationship_type_id for value in changes.update
        }
        relationship_types = await self.people_storage.get_relationship_types_by_ids(
            relationship_type_ids=relationship_type_ids,
            author_username=author_username,
        )
        if len(relationship_types) != len(relationship_type_ids):
            raise PersonRelationshipTypeNotFoundError
        create_pair_keys = [
            (
                min(person_id, value.related_person_id),
                max(person_id, value.related_person_id),
                value.relationship_type_id,
            )
            for value in changes.create
        ]
        update_pair_keys = [
            (
                min(person_id, value.related_person_id),
                max(person_id, value.related_person_id),
                value.relationship_type_id,
            )
            for value in changes.update
        ]
        pair_keys = [*create_pair_keys, *update_pair_keys]
        if len(pair_keys) != len(set(pair_keys)):
            raise KnowledgeConflictError
        return existing_relationships

    async def delete_person(
        self,
        *,
        person_id: str,
        author_username: str,
        current_datetime: datetime,
    ) -> tuple[str, ...]:
        await self.item_service.get_item(
            item_id=person_id,
            author_username=author_username,
            kind=KnowledgeItemKind.PERSON,
        )
        related_ids = await self.people_storage.list_related_person_ids(
            person_id=person_id,
            author_username=author_username,
        )
        related_date_ids = await self.dates_storage.list_date_ids_for_person(
            person_id=person_id,
            author_username=author_username,
        )
        files = await self.file_storage.list_item_files(
            item_id=person_id,
            author_username=author_username,
        )
        object_names_to_delete = await self.file_service.delete_files(files=files)
        await self.item_service.delete_item(
            item_id=person_id,
            author_username=author_username,
            kind=KnowledgeItemKind.PERSON,
        )
        await self.item_storage.touch_items(
            item_ids=related_ids,
            author_username=author_username,
            kind=KnowledgeItemKind.PERSON,
            updated_at=current_datetime,
        )
        await self.item_storage.touch_items(
            item_ids=set(related_date_ids),
            author_username=author_username,
            kind=KnowledgeItemKind.DATE,
            updated_at=current_datetime,
        )
        return object_names_to_delete


@dataclass(kw_only=True, slots=True, frozen=True)
class PersonRelationshipTypesUseCase:
    storage: PeopleStorage

    async def list_relationship_types(
        self,
        *,
        author_username: str,
    ) -> list[PersonRelationshipType]:
        return await self.storage.list_relationship_types(author_username=author_username)

    async def create_relationship_type(
        self,
        *,
        params: PersonRelationshipTypeCreateParams,
        current_datetime: datetime,
    ) -> PersonRelationshipType:
        reverse_name = params.forward_name if params.is_symmetric else params.reverse_name
        normalized_params = PersonRelationshipTypeCreateParams(
            author_username=params.author_username,
            is_symmetric=params.is_symmetric,
            forward_name=params.forward_name,
            reverse_name=reverse_name,
        )
        PersonRelationshipType(
            id="validation",
            author_username=params.author_username,
            is_symmetric=params.is_symmetric,
            forward_name=params.forward_name,
            reverse_name=reverse_name,
            created_at=current_datetime,
            updated_at=current_datetime,
        )
        return await self.storage.create_relationship_type(params=normalized_params)

    async def update_relationship_type(
        self,
        *,
        relationship_type_id: str,
        params: PersonRelationshipTypeUpdateParams,
        author_username: str,
        current_datetime: datetime,
    ) -> PersonRelationshipType:
        relationship_type = await self.storage.get_relationship_type(
            relationship_type_id=relationship_type_id,
            author_username=author_username,
        )
        reverse_name = params.forward_name if params.is_symmetric else params.reverse_name
        normalized_params = PersonRelationshipTypeUpdateParams(
            is_symmetric=params.is_symmetric,
            forward_name=params.forward_name,
            reverse_name=reverse_name,
        )
        PersonRelationshipType(
            id=relationship_type.id,
            author_username=relationship_type.author_username,
            is_symmetric=params.is_symmetric,
            forward_name=params.forward_name,
            reverse_name=reverse_name,
            created_at=relationship_type.created_at,
            updated_at=current_datetime,
        )
        return await self.storage.update_relationship_type(
            relationship_type=relationship_type,
            params=normalized_params,
            updated_at=current_datetime,
        )

    async def delete_relationship_type(
        self,
        *,
        relationship_type_id: str,
        author_username: str,
    ) -> None:
        await self.storage.get_relationship_type(
            relationship_type_id=relationship_type_id,
            author_username=author_username,
        )
        if await self.storage.is_relationship_type_used(
            relationship_type_id=relationship_type_id,
            author_username=author_username,
        ):
            raise KnowledgeConflictError
        await self.storage.delete_relationship_type(
            relationship_type_id=relationship_type_id,
            author_username=author_username,
        )
