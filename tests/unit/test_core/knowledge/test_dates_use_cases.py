from datetime import UTC, datetime
from unittest.mock import Mock, call

import pytest

from core.knowledge.dates.enums import KnowledgeDateListSort
from core.knowledge.dates.schemas import (
    KnowledgeDateCreateParams,
    KnowledgeDateDetails,
    KnowledgeDateFilters,
    KnowledgeDatePersonLink,
    KnowledgeDateUpdateParams,
    KnowledgeDateValue,
)
from core.knowledge.dates.storages import KnowledgeDatesStorage
from core.knowledge.dates.use_cases import KnowledgeDatesUseCase
from core.knowledge.exceptions import PersonNotFoundError
from core.knowledge.files.enums import KnowledgeFileKind, KnowledgeFileProcessing
from core.knowledge.files.schemas import KnowledgeFile
from core.knowledge.files.services import KnowledgeFileCrudService
from core.knowledge.files.storages import KnowledgeFilesStorage
from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.items.schemas import KnowledgeItem, KnowledgeTag
from core.knowledge.items.services import KnowledgeItemCrudService
from core.knowledge.items.storages import KnowledgeItemsStorage
from tests.test_cases import TestCase

CURRENT_DATETIME = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


def knowledge_item(
    *,
    item_id: str,
    kind: KnowledgeItemKind,
    display_name: str,
) -> KnowledgeItem:
    return KnowledgeItem(
        id=item_id,
        kind=kind,
        author_username="owner",
        display_name=display_name,
        description="",
        tags=[],
        created_at=CURRENT_DATETIME,
        updated_at=CURRENT_DATETIME,
    )


class TestKnowledgeDatesUseCase(TestCase):
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.item_service = Mock(spec=KnowledgeItemCrudService)
        self.item_storage = Mock(spec=KnowledgeItemsStorage)
        self.dates_storage = Mock(spec=KnowledgeDatesStorage)
        self.file_storage = Mock(spec=KnowledgeFilesStorage)
        self.file_service = Mock(spec=KnowledgeFileCrudService)
        self.file_storage.list_item_files.return_value = []
        self.use_case = KnowledgeDatesUseCase(
            item_service=self.item_service,
            item_storage=self.item_storage,
            dates_storage=self.dates_storage,
            file_storage=self.file_storage,
            file_service=self.file_service,
        )

    async def test_list_validates_tag_and_person_then_projects_page(self) -> None:
        date_id = self.factory.core.hex_id(1)
        person_id = self.factory.core.hex_id(2)
        tag_id = self.factory.core.hex_id(3)
        date_item = knowledge_item(
            item_id=date_id,
            kind=KnowledgeItemKind.DATE,
            display_name="Годовщина",
        )
        person_item = knowledge_item(
            item_id=person_id,
            kind=KnowledgeItemKind.PERSON,
            display_name="Иван Иванов",
        )
        tag = KnowledgeTag(
            id=tag_id,
            author_username="owner",
            name="Семья",
            created_at=CURRENT_DATETIME,
            updated_at=CURRENT_DATETIME,
        )
        self.item_storage.get_tags_by_ids.return_value = [tag]
        self.item_storage.get_items_by_ids.side_effect = [
            [person_item],
            [date_item],
            [person_item],
        ]
        self.dates_storage.list_date_page.return_value = ([date_id], 1)
        self.dates_storage.list_details.return_value = [
            KnowledgeDateDetails(
                item_id=date_id,
                date=KnowledgeDateValue(day=29, month=2, year=None),
            ),
        ]
        self.dates_storage.list_person_links.return_value = [
            KnowledgeDatePersonLink(date_id=date_id, person_id=person_id),
        ]
        filters = KnowledgeDateFilters(
            page=1,
            page_size=20,
            sort=KnowledgeDateListSort.DATE_ASC,
            search_query="  годов  ",
            tag_ids=(tag_id,),
            related_person_id=person_id,
            author_username="owner",
        )

        page = await self.use_case.list_dates(filters=filters)

        assert page.total_count == 1
        assert page.values[0].date == KnowledgeDateValue(day=29, month=2, year=None)
        assert page.values[0].related_people[0].id == person_id
        self.dates_storage.list_date_page.assert_awaited_once_with(
            filters=KnowledgeDateFilters(
                page=1,
                page_size=20,
                sort=KnowledgeDateListSort.DATE_ASC,
                search_query="годов",
                tag_ids=(tag_id,),
                related_person_id=person_id,
                author_username="owner",
            ),
        )

    async def test_create_uses_typed_item_and_blank_detail_state(self) -> None:
        date_id = self.factory.core.hex_id(1)
        item = knowledge_item(
            item_id=date_id,
            kind=KnowledgeItemKind.DATE,
            display_name="Годовщина",
        )
        self.item_service.create_item.return_value = item
        self.item_service.get_item.return_value = item
        self.dates_storage.get_details.return_value = KnowledgeDateDetails(
            item_id=date_id,
            date=KnowledgeDateValue(day=1, month=5, year=2020),
        )
        self.dates_storage.list_person_links.return_value = []
        self.item_storage.get_items_by_ids.return_value = []

        created = await self.use_case.create_date(
            params=KnowledgeDateCreateParams(
                display_name="  Годовщина  ",
                date=KnowledgeDateValue(day=1, month=5, year=2020),
                author_username="owner",
            ),
            today=CURRENT_DATETIME.date(),
        )

        assert created.item.id == date_id
        create_params = self.item_service.create_item.await_args.kwargs["params"]
        assert create_params.kind == KnowledgeItemKind.DATE
        assert create_params.display_name == "Годовщина"
        assert create_params.description == ""

    async def test_update_rejects_foreign_or_wrong_kind_person_before_mutation(self) -> None:
        date_id = self.factory.core.hex_id(1)
        person_id = self.factory.core.hex_id(2)
        self.item_service.get_item.return_value = knowledge_item(
            item_id=date_id,
            kind=KnowledgeItemKind.DATE,
            display_name="Дата",
        )
        self.dates_storage.get_details.return_value = KnowledgeDateDetails(
            item_id=date_id,
            date=KnowledgeDateValue(day=1, month=1, year=None),
        )
        self.dates_storage.list_person_links.return_value = []
        self.item_storage.get_items_by_ids.return_value = []

        with pytest.raises(PersonNotFoundError):
            await self.use_case.update_date(
                date_id=date_id,
                params=KnowledgeDateUpdateParams(
                    display_name="Дата",
                    date=KnowledgeDateValue(day=2, month=1, year=None),
                    description="",
                    tag_ids=[],
                    person_ids=[person_id],
                ),
                author_username="owner",
                current_datetime=CURRENT_DATETIME,
            )

        self.item_service.update_item.assert_not_called()
        self.dates_storage.replace_person_links.assert_not_called()

    async def test_update_replaces_links_and_touches_old_and_new_people(self) -> None:
        date_id = self.factory.core.hex_id(1)
        old_person_id = self.factory.core.hex_id(2)
        new_person_id = self.factory.core.hex_id(3)
        item = knowledge_item(
            item_id=date_id,
            kind=KnowledgeItemKind.DATE,
            display_name="Дата",
        )
        new_person = knowledge_item(
            item_id=new_person_id,
            kind=KnowledgeItemKind.PERSON,
            display_name="Новый человек",
        )
        self.item_service.get_item.return_value = item
        self.dates_storage.get_details.return_value = KnowledgeDateDetails(
            item_id=date_id,
            date=KnowledgeDateValue(day=2, month=1, year=None),
        )
        self.dates_storage.list_person_links.side_effect = [
            [KnowledgeDatePersonLink(date_id=date_id, person_id=old_person_id)],
            [KnowledgeDatePersonLink(date_id=date_id, person_id=new_person_id)],
        ]
        self.item_storage.get_items_by_ids.side_effect = [[new_person], [new_person]]

        await self.use_case.update_date(
            date_id=date_id,
            params=KnowledgeDateUpdateParams(
                display_name="Дата",
                date=KnowledgeDateValue(day=2, month=1, year=None),
                description="Описание",
                tag_ids=[],
                person_ids=[new_person_id],
            ),
            author_username="owner",
            current_datetime=CURRENT_DATETIME,
        )

        self.dates_storage.replace_person_links.assert_awaited_once_with(
            date_id=date_id,
            person_ids=[new_person_id],
            author_username="owner",
        )
        assert self.item_storage.touch_items.await_args.kwargs["item_ids"] == {
            old_person_id,
            new_person_id,
        }
        assert self.item_storage.touch_items.await_args.kwargs["updated_at"] == CURRENT_DATETIME

    async def test_delete_returns_private_objects_and_touches_people(self) -> None:
        date_id = self.factory.core.hex_id(1)
        person_id = self.factory.core.hex_id(2)
        self.item_service.get_item.return_value = knowledge_item(
            item_id=date_id,
            kind=KnowledgeItemKind.DATE,
            display_name="Дата",
        )
        self.dates_storage.list_person_links.return_value = [
            KnowledgeDatePersonLink(date_id=date_id, person_id=person_id),
        ]
        file = KnowledgeFile(
            id=self.factory.core.hex_id(3),
            item_id=date_id,
            author_username="owner",
            kind=KnowledgeFileKind.ATTACHMENT,
            processing=KnowledgeFileProcessing.RAW,
            relative_path="attachments/file.txt",
            mime_type="text/plain",
            size_bytes=10,
            name="file.txt",
            original_name="file.txt",
            original_sha256="a" * 64,
            created_at=CURRENT_DATETIME,
            updated_at=CURRENT_DATETIME,
        )
        self.file_storage.list_item_files.return_value = [file]
        self.file_service.delete_files.return_value = (file.relative_path,)
        mutations = Mock()
        mutations.attach_mock(self.file_service.delete_files, "delete_files")
        mutations.attach_mock(self.item_service.delete_item, "delete_item")

        object_names = await self.use_case.delete_date(
            date_id=date_id,
            author_username="owner",
            current_datetime=CURRENT_DATETIME,
        )

        assert object_names == ("attachments/file.txt",)
        assert mutations.method_calls == [
            call.delete_files(files=[file]),
            call.delete_item(
                item_id=date_id,
                author_username="owner",
                kind=KnowledgeItemKind.DATE,
            ),
        ]
        assert self.item_storage.touch_items.await_args.kwargs["item_ids"] == {person_id}
        assert self.item_storage.touch_items.await_args.kwargs["updated_at"] == CURRENT_DATETIME
