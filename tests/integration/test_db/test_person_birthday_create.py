from unittest.mock import Mock, patch

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from core.knowledge.files.services import KnowledgeFileCrudService
from core.knowledge.items.services import KnowledgeItemCrudService
from core.knowledge.people.schemas import PersonBirthday, PersonDetails, PersonQuickCreateParams
from core.knowledge.people.use_cases import PeopleUseCase
from infra.postgresql.models import KnowledgeItemModel, PersonDetailsModel
from infra.postgresql.storages.knowledge.dates import KnowledgeDatesDatabaseStorage
from infra.postgresql.storages.knowledge.files import KnowledgeFilesDatabaseStorage
from infra.postgresql.storages.knowledge.items import KnowledgeItemsDatabaseStorage
from infra.postgresql.storages.knowledge.people import PeopleDatabaseStorage
from tests.test_cases import StorageTestCase


class TestPersonBirthdayCreate(StorageTestCase):
    @pytest_asyncio.fixture(autouse=True)
    async def setup(self) -> None:
        items = KnowledgeItemsDatabaseStorage(session=self.db_session)
        self.people_storage = PeopleDatabaseStorage(session=self.db_session)
        self.use_case = PeopleUseCase(
            item_service=KnowledgeItemCrudService(storage=items),
            item_storage=items,
            people_storage=self.people_storage,
            dates_storage=KnowledgeDatesDatabaseStorage(session=self.db_session),
            file_storage=KnowledgeFilesDatabaseStorage(
                session=self.db_session,
                namespace="knowledge-private",
            ),
            file_service=Mock(spec=KnowledgeFileCrudService),
        )

    @pytest.mark.parametrize("birthday", [None, PersonBirthday(day=29, month=2, year=None)])
    async def test_create_retains_names_and_optional_birthday(
        self,
        birthday: PersonBirthday | None,
    ) -> None:
        person = await self.use_case.create_person(
            params=PersonQuickCreateParams(
                author_username="owner",
                first_name="Ivan",
                last_name="Ivanov",
                birthday=birthday,
            ),
        )
        assert person.details.birthday == birthday
        assert person.details.notifications_enabled is True
        assert person.item.display_name == "Ivanov Ivan"
        stored = await self.people_storage.get_details(
            item_id=person.item.id,
            author_username="owner",
        )
        assert stored.birthday == birthday

    async def test_failed_details_roll_back_the_common_item(self) -> None:
        original = self.people_storage.create_details

        async def fail_after_insert(*, details: PersonDetails, author_username: str) -> None:
            await original(details=details, author_username=author_username)
            message = "injected transaction failure"
            raise RuntimeError(message)

        async def create_with_failure() -> None:
            async with self.db_session.begin_nested():
                with patch.object(
                    PeopleDatabaseStorage,
                    "create_details",
                    side_effect=fail_after_insert,
                ):
                    await self.use_case.create_person(
                        params=PersonQuickCreateParams(
                            author_username="owner",
                            first_name="Ivan",
                            last_name="Ivanov",
                            birthday=PersonBirthday(day=29, month=2, year=None),
                        ),
                    )

        with pytest.raises(RuntimeError, match="injected transaction failure"):
            await create_with_failure()
        assert (
            await self.db_session.scalar(select(func.count()).select_from(KnowledgeItemModel)) == 0
        )
        assert (
            await self.db_session.scalar(select(func.count()).select_from(PersonDetailsModel)) == 0
        )
