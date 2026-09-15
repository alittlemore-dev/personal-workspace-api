from datetime import UTC, datetime
from unittest.mock import Mock, call

import pytest

from core.knowledge.dates.schemas import KnowledgeDateDetails, KnowledgeDateValue
from core.knowledge.dates.storages import KnowledgeDatesStorage
from core.knowledge.exceptions import (
    InvalidKnowledgeDataError,
    KnowledgeConflictError,
    KnowledgeTagNotFoundError,
    PersonRelationshipNotFoundError,
    PersonRelationshipTypeNotFoundError,
)
from core.knowledge.files.enums import KnowledgeFileKind, KnowledgeFileProcessing
from core.knowledge.files.schemas import KnowledgeFile
from core.knowledge.files.services import KnowledgeFileCrudService
from core.knowledge.files.storages import KnowledgeFilesStorage
from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.items.schemas import (
    KnowledgeItem,
    KnowledgeTag,
)
from core.knowledge.items.services import KnowledgeItemCrudService
from core.knowledge.items.storages import KnowledgeItemsStorage
from core.knowledge.people.enums import (
    PersonListSort,
    PersonRelationshipDirection,
)
from core.knowledge.people.schemas import (
    PersonDetails,
    PersonFilters,
    PersonRelationship,
    PersonRelationshipChanges,
    PersonRelationshipCreateParams,
    PersonRelationshipType,
    PersonRelationshipTypeUpdateParams,
    PersonRelationshipUpdateParams,
    PersonUpdateParams,
)
from core.knowledge.people.storages import PeopleStorage
from core.knowledge.people.use_cases import PeopleUseCase, PersonRelationshipTypesUseCase
from tests.test_cases import TestCase

CURRENT_DATETIME = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


def knowledge_item(
    *,
    item_id: str,
    display_name: str,
    author_username: str = "owner",
) -> KnowledgeItem:
    return KnowledgeItem(
        id=item_id,
        kind=KnowledgeItemKind.PERSON,
        author_username=author_username,
        display_name=display_name,
        description="",
        tags=[],
        created_at=CURRENT_DATETIME,
        updated_at=CURRENT_DATETIME,
    )


def person_details(
    *,
    item_id: str,
    last_name: str = "Иванов",
    telegram: str = "",
) -> PersonDetails:
    return PersonDetails(
        item_id=item_id,
        last_name=last_name,
        first_name="Иван",
        middle_name="",
        email="",
        phone="",
        telegram=telegram,
        birthday=None,
    )


def relationship_type(*, relationship_type_id: str) -> PersonRelationshipType:
    return PersonRelationshipType(
        id=relationship_type_id,
        author_username="owner",
        is_symmetric=False,
        forward_name="руководитель",
        reverse_name="подчинённый",
        created_at=CURRENT_DATETIME,
        updated_at=CURRENT_DATETIME,
    )


def relationship(
    *,
    relationship_id: str,
    source_person_id: str,
    target_person_id: str,
    type_schema: PersonRelationshipType,
) -> PersonRelationship:
    return PersonRelationship(
        id=relationship_id,
        author_username="owner",
        source_person_id=source_person_id,
        target_person_id=target_person_id,
        relationship_type=type_schema,
        note="",
        created_at=CURRENT_DATETIME,
        updated_at=CURRENT_DATETIME,
    )


class TestKnowledgeItemCrudService(TestCase):
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.storage = Mock(spec=KnowledgeItemsStorage)
        self.service = KnowledgeItemCrudService(storage=self.storage)

    async def test_update_item_replaces_tags_after_typed_item_update(self) -> None:
        item = knowledge_item(
            item_id=self.factory.core.hex_id(1),
            display_name="Иванов Иван",
        )
        tag = KnowledgeTag(
            id=self.factory.core.hex_id(2),
            author_username="owner",
            name="Работа",
            created_at=CURRENT_DATETIME,
            updated_at=CURRENT_DATETIME,
        )
        self.storage.get_tags_by_ids.return_value = [tag]
        self.storage.update_item.return_value = item

        updated = await self.service.update_item(
            item=item,
            params=Mock(),
            tag_ids=[tag.id],
            updated_at=CURRENT_DATETIME,
        )

        assert updated == item
        self.storage.replace_item_tags.assert_awaited_once_with(
            item_id=item.id,
            author_username="owner",
            tag_ids=[tag.id],
        )


class TestPeopleUseCase(TestCase):
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.item_service = Mock(spec=KnowledgeItemCrudService)
        self.item_storage = Mock(spec=KnowledgeItemsStorage)
        self.people_storage = Mock(spec=PeopleStorage)
        self.dates_storage = Mock(spec=KnowledgeDatesStorage)
        self.dates_storage.list_date_ids_for_person.return_value = []
        self.file_storage = Mock(spec=KnowledgeFilesStorage)
        self.file_service = Mock(spec=KnowledgeFileCrudService)
        self.file_storage.list_files_for_items.return_value = []
        self.file_storage.list_item_files.return_value = []
        self.use_case = PeopleUseCase(
            item_service=self.item_service,
            item_storage=self.item_storage,
            people_storage=self.people_storage,
            dates_storage=self.dates_storage,
            file_storage=self.file_storage,
            file_service=self.file_service,
        )

    async def test_get_person_projects_related_dates_in_calendar_order(self) -> None:
        person_id = self.factory.core.hex_id(1)
        january_id = self.factory.core.hex_id(2)
        december_id = self.factory.core.hex_id(3)
        item = knowledge_item(item_id=person_id, display_name="Иванов Иван")
        january_item = KnowledgeItem(
            id=january_id,
            kind=KnowledgeItemKind.DATE,
            author_username="owner",
            display_name="Новый год",
            description="",
            tags=[],
            created_at=CURRENT_DATETIME,
            updated_at=CURRENT_DATETIME,
        )
        december_item = KnowledgeItem(
            id=december_id,
            kind=KnowledgeItemKind.DATE,
            author_username="owner",
            display_name="Годовщина",
            description="",
            tags=[],
            created_at=CURRENT_DATETIME,
            updated_at=CURRENT_DATETIME,
        )
        self.item_service.get_item.return_value = item
        self.people_storage.get_details.return_value = person_details(item_id=person_id)
        self.people_storage.list_relationships.return_value = []
        self.item_storage.get_items_by_ids.side_effect = [
            [],
            [december_item, january_item],
        ]
        self.dates_storage.list_date_ids_for_person.return_value = [
            december_id,
            january_id,
        ]
        self.dates_storage.list_details.return_value = [
            KnowledgeDateDetails(
                item_id=december_id,
                date=KnowledgeDateValue(day=31, month=12, year=None),
            ),
            KnowledgeDateDetails(
                item_id=january_id,
                date=KnowledgeDateValue(day=1, month=1, year=2020),
            ),
        ]

        person = await self.use_case.get_person(
            person_id=person_id,
            author_username="owner",
        )

        assert [value.id for value in person.related_dates] == [january_id, december_id]
        self.item_storage.get_items_by_ids.assert_any_await(
            item_ids={january_id, december_id},
            author_username="owner",
            kind=KnowledgeItemKind.DATE,
        )

    async def test_list_validates_tags_then_fetches_and_reorders_only_page_items(self) -> None:
        first_id = self.factory.core.hex_id(1)
        second_id = self.factory.core.hex_id(2)
        tag_id = self.factory.core.hex_id(3)
        tag = KnowledgeTag(
            id=tag_id,
            author_username="owner",
            name="Work",
            created_at=CURRENT_DATETIME,
            updated_at=CURRENT_DATETIME,
        )
        first_item = knowledge_item(item_id=first_id, display_name="Alpha")
        second_item = knowledge_item(item_id=second_id, display_name="Beta")
        self.item_storage.get_tags_by_ids.return_value = [tag]
        self.people_storage.list_person_page.return_value = ([second_id, first_id], 2)
        self.item_storage.get_items_by_ids.return_value = [first_item, second_item]
        self.people_storage.list_details.return_value = [
            person_details(item_id=first_id, last_name="Alpha"),
            person_details(item_id=second_id, last_name="Beta", telegram="@beta"),
        ]
        filters = PersonFilters(
            page=2,
            page_size=50,
            sort=PersonListSort.NAME_DESC,
            search_query="  example.com  ",
            tag_ids=(tag_id,),
            author_username="owner",
        )

        page = await self.use_case.list_people(filters=filters)

        assert [person.id for person in page.values] == [second_id, first_id]
        assert page.values[0].telegram == "@beta"
        assert page.total_count == 2
        self.item_storage.get_tags_by_ids.assert_awaited_once_with(
            tag_ids={tag_id},
            author_username="owner",
        )
        self.people_storage.list_person_page.assert_awaited_once_with(
            filters=PersonFilters(
                page=2,
                page_size=50,
                sort=PersonListSort.NAME_DESC,
                search_query="example.com",
                tag_ids=(tag_id,),
                author_username="owner",
            ),
        )
        self.item_storage.get_items_by_ids.assert_awaited_once_with(
            item_ids={first_id, second_id},
            author_username="owner",
            kind=KnowledgeItemKind.PERSON,
        )

    async def test_list_rejects_tag_not_owned_by_author_before_page_query(self) -> None:
        tag_id = self.factory.core.hex_id(1)
        self.item_storage.get_tags_by_ids.return_value = []
        filters = PersonFilters(
            page=1,
            page_size=20,
            sort=PersonListSort.UPDATED_NEWEST,
            search_query=None,
            tag_ids=(tag_id,),
            author_username="owner",
        )

        with pytest.raises(KnowledgeTagNotFoundError):
            await self.use_case.list_people(filters=filters)

        self.people_storage.list_person_page.assert_not_called()
        self.item_storage.get_items_by_ids.assert_not_called()

    async def test_update_relationship_touches_old_and_new_related_people(self) -> None:
        person_id = self.factory.core.hex_id(1)
        old_related_id = self.factory.core.hex_id(2)
        new_related_id = self.factory.core.hex_id(3)
        relationship_id = self.factory.core.hex_id(4)
        relationship_type_id = self.factory.core.hex_id(5)
        item = knowledge_item(item_id=person_id, display_name="Иванов Иван")
        new_related_item = knowledge_item(
            item_id=new_related_id,
            display_name="Петров Пётр",
        )
        type_schema = relationship_type(relationship_type_id=relationship_type_id)
        old_relationship = relationship(
            relationship_id=relationship_id,
            source_person_id=person_id,
            target_person_id=old_related_id,
            type_schema=type_schema,
        )
        self.item_service.get_item.return_value = item
        self.people_storage.get_details.return_value = person_details(item_id=person_id)
        self.people_storage.get_relationships_by_ids.return_value = [old_relationship]
        self.people_storage.get_relationship_types_by_ids.return_value = [type_schema]
        self.item_storage.get_items_by_ids.side_effect = [[new_related_item], []]
        self.people_storage.list_relationships.return_value = []
        params = PersonUpdateParams(
            last_name="Иванов",
            first_name="Иван",
            middle_name="",
            email="",
            phone="",
            telegram="",
            birthday=None,
            description="",
            tag_ids=[],
            relationship_changes=PersonRelationshipChanges(
                create=[],
                update=[
                    PersonRelationshipUpdateParams(
                        id=relationship_id,
                        related_person_id=new_related_id,
                        relationship_type_id=relationship_type_id,
                        direction=PersonRelationshipDirection.FORWARD,
                        note="перенесено",
                    ),
                ],
                delete_ids=[],
            ),
        )

        await self.use_case.update_person(
            person_id=person_id,
            params=params,
            author_username="owner",
            current_datetime=CURRENT_DATETIME,
        )

        touch_call = self.item_storage.touch_items.await_args
        assert touch_call.kwargs["item_ids"] == {old_related_id, new_related_id}
        assert touch_call.kwargs["updated_at"] == CURRENT_DATETIME
        self.people_storage.update_relationships.assert_awaited_once()

    async def test_delete_person_reuses_supplied_datetime_for_every_touched_item(self) -> None:
        person_id = self.factory.core.hex_id(1)
        related_person_id = self.factory.core.hex_id(2)
        related_date_id = self.factory.core.hex_id(3)
        self.item_service.get_item.return_value = knowledge_item(
            item_id=person_id,
            display_name="Иванов Иван",
        )
        self.people_storage.list_related_person_ids.return_value = {related_person_id}
        self.dates_storage.list_date_ids_for_person.return_value = [related_date_id]

        await self.use_case.delete_person(
            person_id=person_id,
            author_username="owner",
            current_datetime=CURRENT_DATETIME,
        )

        assert self.item_storage.touch_items.await_count == 2
        assert {
            call.kwargs["updated_at"] for call in self.item_storage.touch_items.await_args_list
        } == {CURRENT_DATETIME}

    async def test_delete_person_removes_file_metadata_before_item_and_returns_object_path(
        self,
    ) -> None:
        person_id = self.factory.core.hex_id(1)
        file = KnowledgeFile(
            id=self.factory.core.hex_id(2),
            item_id=person_id,
            author_username="owner",
            kind=KnowledgeFileKind.PERSON_PHOTO,
            processing=KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE,
            relative_path="person-photos/photo.webp",
            mime_type="image/webp",
            size_bytes=10,
            name="Photo",
            original_name="photo.png",
            original_sha256="a" * 64,
            created_at=CURRENT_DATETIME,
            updated_at=CURRENT_DATETIME,
        )
        self.item_service.get_item.return_value = knowledge_item(
            item_id=person_id,
            display_name="Иванов Иван",
        )
        self.people_storage.list_related_person_ids.return_value = set()
        self.dates_storage.list_date_ids_for_person.return_value = []
        self.file_storage.list_item_files.return_value = [file]
        self.file_service.delete_files.return_value = (file.relative_path,)
        mutations = Mock()
        mutations.attach_mock(self.file_service.delete_files, "delete_files")
        mutations.attach_mock(self.item_service.delete_item, "delete_item")

        object_names = await self.use_case.delete_person(
            person_id=person_id,
            author_username="owner",
            current_datetime=CURRENT_DATETIME,
        )

        assert object_names == ("person-photos/photo.webp",)
        assert mutations.method_calls == [
            call.delete_files(files=[file]),
            call.delete_item(
                item_id=person_id,
                author_username="owner",
                kind=KnowledgeItemKind.PERSON,
            ),
        ]

    async def test_delete_person_omits_cleanup_path_when_file_stays_in_use(self) -> None:
        person_id = self.factory.core.hex_id(1)
        file = KnowledgeFile(
            id=self.factory.core.hex_id(2),
            item_id=person_id,
            author_username="owner",
            kind=KnowledgeFileKind.PERSON_PHOTO,
            processing=KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE,
            relative_path="person-photos/photo.webp",
            mime_type="image/webp",
            size_bytes=10,
            name="Photo",
            original_name="photo.png",
            original_sha256="a" * 64,
            created_at=CURRENT_DATETIME,
            updated_at=CURRENT_DATETIME,
        )
        self.item_service.get_item.return_value = knowledge_item(
            item_id=person_id,
            display_name="Иванов Иван",
        )
        self.people_storage.list_related_person_ids.return_value = set()
        self.dates_storage.list_date_ids_for_person.return_value = []
        self.file_storage.list_item_files.return_value = [file]
        self.file_service.delete_files.return_value = ()

        object_names = await self.use_case.delete_person(
            person_id=person_id,
            author_username="owner",
            current_datetime=CURRENT_DATETIME,
        )

        assert object_names == ()

    async def test_validate_relationship_changes_rejects_self_link(self) -> None:
        person_id = self.factory.core.hex_id(1)
        changes = PersonRelationshipChanges(
            create=[
                PersonRelationshipCreateParams(
                    related_person_id=person_id,
                    relationship_type_id=self.factory.core.hex_id(2),
                    direction=PersonRelationshipDirection.FORWARD,
                    note="",
                ),
            ],
            update=[],
            delete_ids=[],
        )
        self.people_storage.get_relationships_by_ids.return_value = []

        with pytest.raises(InvalidKnowledgeDataError):
            await self.use_case.validate_relationship_changes(
                person_id=person_id,
                changes=changes,
                author_username="owner",
            )

    async def test_validate_relationship_changes_rejects_foreign_person_or_type(self) -> None:
        person_id = self.factory.core.hex_id(1)
        changes = PersonRelationshipChanges(
            create=[
                PersonRelationshipCreateParams(
                    related_person_id=self.factory.core.hex_id(2),
                    relationship_type_id=self.factory.core.hex_id(3),
                    direction=PersonRelationshipDirection.FORWARD,
                    note="",
                ),
            ],
            update=[],
            delete_ids=[],
        )
        self.people_storage.get_relationships_by_ids.return_value = []
        self.item_storage.get_items_by_ids.return_value = []

        with pytest.raises(PersonRelationshipNotFoundError):
            await self.use_case.validate_relationship_changes(
                person_id=person_id,
                changes=changes,
                author_username="owner",
            )

        self.item_storage.get_items_by_ids.return_value = [
            knowledge_item(
                item_id=self.factory.core.hex_id(2),
                display_name="Петров Пётр",
            ),
        ]
        self.people_storage.get_relationship_types_by_ids.return_value = []

        with pytest.raises(PersonRelationshipTypeNotFoundError):
            await self.use_case.validate_relationship_changes(
                person_id=person_id,
                changes=changes,
                author_username="owner",
            )

    async def test_validate_relationship_changes_rejects_duplicate_pair_and_type(self) -> None:
        person_id = self.factory.core.hex_id(1)
        related_id = self.factory.core.hex_id(2)
        relationship_type_id = self.factory.core.hex_id(3)
        create = PersonRelationshipCreateParams(
            related_person_id=related_id,
            relationship_type_id=relationship_type_id,
            direction=PersonRelationshipDirection.FORWARD,
            note="",
        )
        changes = PersonRelationshipChanges(
            create=[create, create],
            update=[],
            delete_ids=[],
        )
        self.people_storage.get_relationships_by_ids.return_value = []
        self.item_storage.get_items_by_ids.return_value = [
            knowledge_item(item_id=related_id, display_name="Петров Пётр"),
        ]
        self.people_storage.get_relationship_types_by_ids.return_value = [
            relationship_type(relationship_type_id=relationship_type_id),
        ]

        with pytest.raises(KnowledgeConflictError):
            await self.use_case.validate_relationship_changes(
                person_id=person_id,
                changes=changes,
                author_username="owner",
            )


class TestPersonRelationshipTypesUseCase(TestCase):
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.storage = Mock(spec=PeopleStorage)
        self.use_case = PersonRelationshipTypesUseCase(storage=self.storage)

    async def test_update_reuses_supplied_datetime_for_validation_and_storage(self) -> None:
        relationship_type_id = self.factory.core.hex_id(1)
        existing = relationship_type(relationship_type_id=relationship_type_id)
        self.storage.get_relationship_type.return_value = existing
        self.storage.update_relationship_type.return_value = existing

        await self.use_case.update_relationship_type(
            relationship_type_id=relationship_type_id,
            params=PersonRelationshipTypeUpdateParams(
                is_symmetric=False,
                forward_name="руководитель",
                reverse_name="подчинённый",
            ),
            author_username="owner",
            current_datetime=CURRENT_DATETIME,
        )

        assert (
            self.storage.update_relationship_type.await_args.kwargs["updated_at"]
            == CURRENT_DATETIME
        )
