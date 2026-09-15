from dataclasses import dataclass, replace
from datetime import date, datetime

from core.knowledge.dates.schemas import (
    KnowledgeDate,
    KnowledgeDateCreateParams,
    KnowledgeDateDetails,
    KnowledgeDateFilters,
    KnowledgeDateReference,
    KnowledgeDatesPage,
    KnowledgeDateSummary,
    KnowledgeDateUpdateParams,
    RelatedPerson,
)
from core.knowledge.dates.storages import KnowledgeDatesStorage
from core.knowledge.exceptions import KnowledgeTagNotFoundError, PersonNotFoundError
from core.knowledge.files.enums import KnowledgeFileKind
from core.knowledge.files.services import KnowledgeFileCrudService
from core.knowledge.files.storages import KnowledgeFilesStorage
from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.items.schemas import KnowledgeItemCreateParams, KnowledgeItemUpdateParams
from core.knowledge.items.services import KnowledgeItemCrudService
from core.knowledge.items.storages import KnowledgeItemsStorage


@dataclass(kw_only=True, slots=True, frozen=True)
class KnowledgeDatesUseCase:
    item_service: KnowledgeItemCrudService
    item_storage: KnowledgeItemsStorage
    dates_storage: KnowledgeDatesStorage
    file_storage: KnowledgeFilesStorage
    file_service: KnowledgeFileCrudService

    async def list_dates(self, *, filters: KnowledgeDateFilters) -> KnowledgeDatesPage:
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
        if effective_filters.related_person_id is not None:
            people = await self.item_storage.get_items_by_ids(
                item_ids={effective_filters.related_person_id},
                author_username=effective_filters.author_username,
                kind=KnowledgeItemKind.PERSON,
            )
            if len(people) != 1:
                raise PersonNotFoundError
        page_item_ids, total_count = await self.dates_storage.list_date_page(
            filters=effective_filters,
        )
        unordered_items = await self.item_storage.get_items_by_ids(
            item_ids=set(page_item_ids),
            author_username=effective_filters.author_username,
            kind=KnowledgeItemKind.DATE,
        )
        items_by_id = {item.id: item for item in unordered_items}
        items = [items_by_id[item_id] for item_id in page_item_ids]
        details = await self.dates_storage.list_details(
            item_ids=[item.id for item in items],
            author_username=effective_filters.author_username,
        )
        details_by_id = {value.item_id: value for value in details}
        links = await self.dates_storage.list_person_links(
            date_ids={item.id for item in items},
            author_username=effective_filters.author_username,
        )
        people = await self.item_storage.get_items_by_ids(
            item_ids={link.person_id for link in links},
            author_username=effective_filters.author_username,
            kind=KnowledgeItemKind.PERSON,
        )
        people_by_id = {person.id: person for person in people}
        related_people_by_date: dict[str, list[RelatedPerson]] = {item.id: [] for item in items}
        for link in links:
            person = people_by_id[link.person_id]
            related_people_by_date[link.date_id].append(
                RelatedPerson(id=person.id, display_name=person.display_name),
            )
        for values in related_people_by_date.values():
            values.sort(key=lambda value: (value.display_name.casefold(), value.id))
        return KnowledgeDatesPage.from_values(
            values=[
                KnowledgeDateSummary(
                    id=item.id,
                    display_name=item.display_name,
                    date=details_by_id[item.id].date,
                    related_people=related_people_by_date[item.id],
                    tags=item.tags,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                )
                for item in items
            ],
            total_count=total_count,
            page_size=effective_filters.page_size,
        )

    async def get_date(self, *, date_id: str, author_username: str) -> KnowledgeDate:
        item = await self.item_service.get_item(
            item_id=date_id,
            author_username=author_username,
            kind=KnowledgeItemKind.DATE,
        )
        details = await self.dates_storage.get_details(
            item_id=date_id,
            author_username=author_username,
        )
        links = await self.dates_storage.list_person_links(
            date_ids={date_id},
            author_username=author_username,
        )
        people = await self.item_storage.get_items_by_ids(
            item_ids={link.person_id for link in links},
            author_username=author_username,
            kind=KnowledgeItemKind.PERSON,
        )
        files = await self.file_storage.list_item_files(
            item_id=date_id,
            author_username=author_username,
        )
        return KnowledgeDate(
            item=item,
            details=details,
            related_people=sorted(
                [
                    RelatedPerson(id=person.id, display_name=person.display_name)
                    for person in people
                ],
                key=lambda value: (value.display_name.casefold(), value.id),
            ),
            attachments=[file for file in files if file.kind == KnowledgeFileKind.ATTACHMENT],
        )

    async def create_date(self, *, params: KnowledgeDateCreateParams, today: date) -> KnowledgeDate:
        params.date.validate(today=today)
        item = await self.item_service.create_item(
            params=KnowledgeItemCreateParams(
                kind=KnowledgeItemKind.DATE,
                author_username=params.author_username,
                display_name=params.display_name.strip(),
                description="",
            ),
        )
        await self.dates_storage.create_details(
            details=KnowledgeDateDetails(item_id=item.id, date=params.date),
            author_username=params.author_username,
        )
        return await self.get_date(date_id=item.id, author_username=params.author_username)

    async def update_date(
        self,
        *,
        date_id: str,
        params: KnowledgeDateUpdateParams,
        author_username: str,
        current_datetime: datetime,
    ) -> KnowledgeDate:
        params.date.validate(today=current_datetime.date())
        item = await self.item_service.get_item(
            item_id=date_id,
            author_username=author_username,
            kind=KnowledgeItemKind.DATE,
        )
        await self.dates_storage.get_details(
            item_id=date_id,
            author_username=author_username,
        )
        existing_links = await self.dates_storage.list_person_links(
            date_ids={date_id},
            author_username=author_username,
        )
        people = await self.item_storage.get_items_by_ids(
            item_ids=set(params.person_ids),
            author_username=author_username,
            kind=KnowledgeItemKind.PERSON,
        )
        if len(people) != len(set(params.person_ids)):
            raise PersonNotFoundError
        await self.item_service.update_item(
            item=item,
            params=KnowledgeItemUpdateParams(
                display_name=params.display_name.strip(),
                description=params.description,
            ),
            tag_ids=params.tag_ids,
            updated_at=current_datetime,
        )
        await self.dates_storage.update_details(
            details=KnowledgeDateDetails(item_id=date_id, date=params.date),
            author_username=author_username,
        )
        await self.dates_storage.replace_person_links(
            date_id=date_id,
            person_ids=params.person_ids,
            author_username=author_username,
        )
        await self.item_storage.touch_items(
            item_ids={link.person_id for link in existing_links} | set(params.person_ids),
            author_username=author_username,
            kind=KnowledgeItemKind.PERSON,
            updated_at=current_datetime,
        )
        return await self.get_date(date_id=date_id, author_username=author_username)

    async def delete_date(
        self,
        *,
        date_id: str,
        author_username: str,
        current_datetime: datetime,
    ) -> tuple[str, ...]:
        await self.item_service.get_item(
            item_id=date_id,
            author_username=author_username,
            kind=KnowledgeItemKind.DATE,
        )
        links = await self.dates_storage.list_person_links(
            date_ids={date_id},
            author_username=author_username,
        )
        files = await self.file_storage.list_item_files(
            item_id=date_id,
            author_username=author_username,
        )
        object_names_to_delete = await self.file_service.delete_files(files=files)
        await self.item_service.delete_item(
            item_id=date_id,
            author_username=author_username,
            kind=KnowledgeItemKind.DATE,
        )
        await self.item_storage.touch_items(
            item_ids={link.person_id for link in links},
            author_username=author_username,
            kind=KnowledgeItemKind.PERSON,
            updated_at=current_datetime,
        )
        return object_names_to_delete

    async def list_date_references_for_person(
        self,
        *,
        person_id: str,
        author_username: str,
    ) -> list[KnowledgeDateReference]:
        people = await self.item_storage.get_items_by_ids(
            item_ids={person_id},
            author_username=author_username,
            kind=KnowledgeItemKind.PERSON,
        )
        if len(people) != 1:
            raise PersonNotFoundError
        date_ids = await self.dates_storage.list_date_ids_for_person(
            person_id=person_id,
            author_username=author_username,
        )
        items = await self.item_storage.get_items_by_ids(
            item_ids=set(date_ids),
            author_username=author_username,
            kind=KnowledgeItemKind.DATE,
        )
        items_by_id = {item.id: item for item in items}
        details = await self.dates_storage.list_details(
            item_ids=date_ids,
            author_username=author_username,
        )
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
