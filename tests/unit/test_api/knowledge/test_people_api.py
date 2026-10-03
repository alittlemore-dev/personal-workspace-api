from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import codes

from core.knowledge.exceptions import KnowledgeItemNotFoundError
from core.knowledge.people.enums import PersonListSort
from core.knowledge.people.schemas import (
    PeoplePage,
    PersonFilters,
    PersonQuickCreateParams,
    PersonTargetParams,
    PersonUpdateParams,
)
from entrypoints.litestar.api.knowledge.people.endpoints import PeopleApiController
from tests.test_cases import ApiTestCase
from tests.unit.conftest import TEST_USERNAME

CURRENT_DATETIME = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


def update_payload() -> dict[str, object]:
    return {
        "lastName": "Ivanov",
        "firstName": "Ivan",
        "middleName": "",
        "email": "",
        "phone": "",
        "telegram": "",
        "birthday": None,
        "description": "",
        "tagIds": [],
        "relationshipChanges": {"create": [], "update": [], "deleteIds": []},
        "notificationsEnabled": True,
    }


class TestPeopleApi(ApiTestCase):
    @pytest_asyncio.fixture(autouse=True)
    async def setup(self) -> None:
        self.use_case = await self.container.get_people_use_case()

    def test_list_requires_explicit_pagination_and_sort(self) -> None:
        for response in (
            self.api.get_people(page=None),
            self.api.get_people(page_size=None),
            self.api.get_people(sort=None),
        ):
            self.asserts.status(response=response, expected_status=codes.BAD_REQUEST)

        self.use_case.list_people.assert_not_awaited()

    def test_list_maps_current_author_filters(self) -> None:
        self.use_case.list_people.return_value = PeoplePage(
            values=[],
            total_count=0,
            total_pages=0,
        )

        response = self.api.get_people(
            page=2,
            page_size=50,
            sort="nameDesc",
            search_query="  Ivan  ",
            tag_ids=["1" * 32, "2" * 32, "1" * 32],
        )

        self.asserts.status(response=response, expected_status=codes.OK)
        assert response.headers["cache-control"] == "no-store"
        self.use_case.list_people.assert_awaited_once_with(
            filters=PersonFilters(
                page=2,
                page_size=50,
                sort=PersonListSort.NAME_DESC,
                search_query="Ivan",
                tag_ids=("1" * 32, "2" * 32),
                author_username=TEST_USERNAME,
            ),
        )

    def test_list_normalizes_blank_search_to_absent_filter(self) -> None:
        self.use_case.list_people.return_value = PeoplePage(
            values=[],
            total_count=0,
            total_pages=0,
        )

        response = self.api.get_people(search_query="   ")

        self.asserts.status(response=response, expected_status=codes.OK)
        self.use_case.list_people.assert_awaited_once_with(
            filters=PersonFilters(
                page=1,
                page_size=20,
                sort=PersonListSort.UPDATED_NEWEST,
                search_query=None,
                tag_ids=(),
                author_username=TEST_USERNAME,
            ),
        )

    def test_quick_create_maps_names_and_current_author(self) -> None:
        self.use_case.create_person.return_value = self.factory.core.person(now=CURRENT_DATETIME)

        response = self.api.post_person(
            data={"firstName": "Ivan", "lastName": "Ivanov"},
        )

        self.asserts.status(response=response, expected_status=codes.CREATED)
        assert response.json()["middleName"] == ""
        self.use_case.create_person.assert_awaited_once_with(
            params=PersonQuickCreateParams(
                birthday=None,
                first_name="Ivan",
                last_name="Ivanov",
                author_username=TEST_USERNAME,
            ),
        )

    def test_quick_create_accepts_birthday_without_year(self) -> None:
        self.use_case.create_person.return_value = self.factory.core.person(now=CURRENT_DATETIME)
        response = self.api.post_person(
            data={
                "firstName": "Ivan",
                "lastName": "Ivanov",
                "birthday": {"day": 29, "month": 2, "year": None},
            },
        )
        assert response.status_code == codes.CREATED
        params = self.use_case.create_person.await_args.kwargs["params"]
        assert params.birthday.day == 29
        assert params.birthday.month == 2
        assert params.birthday.year is None

    @pytest.mark.parametrize(
        "birthday",
        [
            None,
            {"day": 30, "month": 2, "year": None},
            {"day": 1, "month": 1, "year": 9999},
            {"day": 29, "month": 2, "year": 2025},
        ],
    )
    def test_invalid_birthday_does_not_fall_back_to_name_only(self, birthday: object) -> None:
        response = self.api.post_person(
            data={
                "firstName": "Ivan",
                "lastName": "Ivanov",
                "birthday": birthday,
            },
        )
        assert response.status_code == codes.BAD_REQUEST
        self.use_case.create_person.assert_not_awaited()

    @pytest.mark.parametrize(
        "payload",
        [
            {"lastName": "Ivanov"},
            {"firstName": "Ivan"},
            {"firstName": "   ", "lastName": "Ivanov"},
        ],
    )
    def test_quick_create_rejects_missing_or_blank_names(
        self,
        payload: dict[str, str],
    ) -> None:
        response = self.api.post_person(data=payload)

        self.asserts.status(response=response, expected_status=codes.BAD_REQUEST)
        self.use_case.create_person.assert_not_awaited()

    def test_update_maps_explicit_relationship_batch(self) -> None:
        self.use_case.update_person.return_value = self.factory.core.person(now=CURRENT_DATETIME)
        payload = update_payload()
        payload["relationshipChanges"] = {
            "create": [
                {
                    "relatedPersonId": "2" * 32,
                    "relationshipTypeId": "3" * 32,
                    "direction": "forward",
                    "note": "",
                },
            ],
            "update": [],
            "deleteIds": ["4" * 32],
        }

        response = self.api.put_person(person_id=1, data=payload)

        self.asserts.status(response=response, expected_status=codes.OK)
        call = self.use_case.update_person.await_args.kwargs["params"]
        assert call.person_id == "0" * 31 + "1"
        assert call.author_username == TEST_USERNAME
        assert isinstance(call.data, PersonUpdateParams)
        assert call.data.relationship_changes.delete_ids == ["4" * 32]
        assert call.data.relationship_changes.create[0].related_person_id == "2" * 32

    @pytest.mark.parametrize(
        ("birthday", "expected_status"),
        [
            (None, codes.OK),
            ({"day": 29, "month": 2, "year": None}, codes.OK),
            ({"day": 29, "month": 2, "year": 2024}, codes.OK),
            ({"day": 31, "month": 4, "year": None}, codes.BAD_REQUEST),
            ({"day": 29, "month": 2, "year": 2025}, codes.BAD_REQUEST),
            ({"day": 28, "month": 7, "year": 9999}, codes.BAD_REQUEST),
        ],
    )
    def test_update_validates_birthday(
        self,
        birthday: dict[str, int | None] | None,
        expected_status: int,
    ) -> None:
        self.use_case.update_person.return_value = self.factory.core.person(now=CURRENT_DATETIME)
        payload = update_payload()
        payload["birthday"] = birthday

        response = self.api.put_person(person_id=1, data=payload)

        self.asserts.status(response=response, expected_status=expected_status)
        if expected_status == codes.OK:
            self.use_case.update_person.assert_awaited_once()
        else:
            self.use_case.update_person.assert_not_awaited()

    @pytest.mark.parametrize("telegram", [None, "t" * 256])
    def test_update_requires_storage_safe_telegram(
        self,
        telegram: str | None,
    ) -> None:
        payload = update_payload()
        if telegram is None:
            del payload["telegram"]
        else:
            payload["telegram"] = telegram

        response = self.api.put_person(person_id=1, data=payload)

        self.asserts.status(response=response, expected_status=codes.BAD_REQUEST)
        self.use_case.update_person.assert_not_awaited()

    def test_get_foreign_or_missing_person_uses_same_not_found_contract(self) -> None:
        self.use_case.get_person.side_effect = KnowledgeItemNotFoundError()

        response = self.api.get_person(person_id=404)

        self.asserts.error_message(
            response=response,
            expected_status=codes.NOT_FOUND,
            expected_message=KnowledgeItemNotFoundError.message,
        )
        self.use_case.get_person.assert_awaited_once_with(
            params=PersonTargetParams(
                person_id=self.factory.core.hex_id(404),
                author_username=TEST_USERNAME,
            ),
        )

    def test_delete_forwards_request_datetime(self) -> None:
        self.use_case.delete_person.return_value = ()

        response = self.api.delete_person(person_id=1)

        self.asserts.status(response=response, expected_status=codes.NO_CONTENT)
        call = self.use_case.delete_person.await_args.kwargs["params"]
        assert call.person_id == self.factory.core.hex_id(1)
        assert call.author_username == TEST_USERNAME
        assert isinstance(call.current_datetime, datetime)

    def test_private_controller_is_uncached(self) -> None:
        assert PeopleApiController.response_headers == {"Cache-Control": "no-store"}
