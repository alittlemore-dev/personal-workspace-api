from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import codes

from core.knowledge.dates.enums import KnowledgeDateListSort
from core.knowledge.dates.schemas import (
    KnowledgeDate,
    KnowledgeDateCreateParams,
    KnowledgeDateDetails,
    KnowledgeDateFilters,
    KnowledgeDatesPage,
    KnowledgeDateUpdateParams,
    KnowledgeDateValue,
)
from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.items.schemas import KnowledgeItem
from entrypoints.litestar.api.knowledge.dates.endpoints import (
    KnowledgeDatesApiController,
)
from tests.test_cases import ApiTestCase
from tests.unit.conftest import TEST_OWNER_USERNAME

CURRENT_DATETIME = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


def date_response(*, date_id: str = "1" * 32) -> KnowledgeDate:
    return KnowledgeDate(
        item=KnowledgeItem(
            id=date_id,
            kind=KnowledgeItemKind.DATE,
            author_username="test",
            display_name="Anniversary",
            description="",
            tags=[],
            created_at=CURRENT_DATETIME,
            updated_at=CURRENT_DATETIME,
        ),
        details=KnowledgeDateDetails(
            item_id=date_id,
            date=KnowledgeDateValue(day=29, month=2, year=None),
        ),
        related_people=[],
        attachments=[],
    )


class TestKnowledgeDatesApi(ApiTestCase):
    @pytest_asyncio.fixture(autouse=True)
    async def setup(self) -> None:
        self.use_case = await self.container.get_knowledge_dates_use_case()

    def test_list_requires_explicit_pagination_and_sort(self) -> None:
        for response in (
            self.api.get_knowledge_dates(page=None),
            self.api.get_knowledge_dates(page_size=None),
            self.api.get_knowledge_dates(sort=None),
        ):
            self.asserts.status(response=response, expected_status=codes.BAD_REQUEST)

        self.use_case.list_dates.assert_not_awaited()

    def test_list_maps_all_private_filters(self) -> None:
        self.use_case.list_dates.return_value = KnowledgeDatesPage(
            values=[],
            total_count=0,
            total_pages=0,
        )

        response = self.api.get_knowledge_dates(
            page=2,
            page_size=50,
            sort="dateDesc",
            search_query="  anniversary  ",
            tag_ids=["1" * 32, "1" * 32, "2" * 32],
            related_person_id="3" * 32,
        )

        self.asserts.status(response=response, expected_status=codes.OK)
        assert response.headers["cache-control"] == "no-store"
        self.use_case.list_dates.assert_awaited_once_with(
            filters=KnowledgeDateFilters(
                page=2,
                page_size=50,
                sort=KnowledgeDateListSort.DATE_DESC,
                search_query="anniversary",
                tag_ids=("1" * 32, "2" * 32),
                related_person_id="3" * 32,
                author_username=TEST_OWNER_USERNAME,
            ),
        )

    def test_create_maps_required_fields_and_current_author(self) -> None:
        self.use_case.create_date.return_value = date_response()

        response = self.api.post_knowledge_date(
            data={
                "displayName": "Anniversary",
                "date": {"day": 29, "month": 2, "year": None},
            },
        )

        self.asserts.status(response=response, expected_status=codes.CREATED)
        call = self.use_case.create_date.await_args.kwargs
        assert call["params"] == KnowledgeDateCreateParams(
            display_name="Anniversary",
            date=KnowledgeDateValue(day=29, month=2, year=None),
            author_username=TEST_OWNER_USERNAME,
        )
        assert call["today"] == datetime(2026, 7, 27, tzinfo=UTC).date()

    @pytest.mark.parametrize(
        ("date_value", "expected_status"),
        [
            ({"day": 29, "month": 2, "year": None}, codes.CREATED),
            ({"day": 29, "month": 2, "year": 2024}, codes.CREATED),
            ({"day": 31, "month": 4, "year": None}, codes.BAD_REQUEST),
            ({"day": 29, "month": 2, "year": 2025}, codes.BAD_REQUEST),
            ({"day": 31, "month": 7, "year": 9999}, codes.BAD_REQUEST),
        ],
    )
    def test_create_validates_calendar_date(
        self,
        date_value: dict[str, int | None],
        expected_status: int,
    ) -> None:
        self.use_case.create_date.return_value = date_response()

        response = self.api.post_knowledge_date(
            data={"displayName": "Anniversary", "date": date_value},
        )

        self.asserts.status(response=response, expected_status=expected_status)
        if expected_status == codes.CREATED:
            self.use_case.create_date.assert_awaited_once()
        else:
            self.use_case.create_date.assert_not_awaited()

    def test_update_maps_people_tags_and_rejects_duplicate_people(self) -> None:
        self.use_case.update_date.return_value = date_response()
        payload = {
            "displayName": "Anniversary",
            "date": {"day": 29, "month": 2, "year": None},
            "description": "",
            "tagIds": ["2" * 32],
            "personIds": ["3" * 32],
        }

        response = self.api.put_knowledge_date(date_id=1, data=payload)

        self.asserts.status(response=response, expected_status=codes.OK)
        call = self.use_case.update_date.await_args.kwargs
        assert call["date_id"] == "0" * 31 + "1"
        assert call["params"] == KnowledgeDateUpdateParams(
            display_name="Anniversary",
            date=KnowledgeDateValue(day=29, month=2, year=None),
            description="",
            tag_ids=["2" * 32],
            person_ids=["3" * 32],
        )
        assert call["author_username"] == TEST_OWNER_USERNAME

        payload["personIds"] = ["3" * 32, "3" * 32]
        duplicate = self.api.put_knowledge_date(date_id=1, data=payload)
        self.asserts.status(response=duplicate, expected_status=codes.BAD_REQUEST)

    def test_private_controller_is_hidden_and_uncached(self) -> None:
        assert KnowledgeDatesApiController.include_in_schema is False
        assert KnowledgeDatesApiController.response_headers == {
            "Cache-Control": "no-store",
        }
