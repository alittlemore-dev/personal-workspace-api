from datetime import date

import pytest
import pytest_asyncio
from httpx import codes

from core.calendar.enums import CalendarWindow
from core.calendar.schemas import (
    GetCalendarParams,
)
from entrypoints.litestar.api.calendar.endpoints import CalendarApiController
from tests.test_cases import ApiTestCase
from tests.unit.conftest import TEST_USERNAME


class TestCalendarApi(ApiTestCase):
    @pytest_asyncio.fixture(autouse=True)
    async def setup(self) -> None:
        self.use_case = await self.container.get_calendar_use_case()

    def test_requires_query_parameters_and_maps_private_calendar(self) -> None:
        missing = self.api.get_calendar(reference_date=None, window=None)
        self.asserts.status(response=missing, expected_status=codes.BAD_REQUEST)
        self.use_case.get_calendar.assert_not_called()
        self.use_case.get_calendar.return_value = self.factory.core.calendar()

        response = self.api.get_calendar(
            reference_date="2026-07-31",
            window="currentAndNextMonths",
        )

        self.asserts.status(response=response, expected_status=codes.OK)
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {
            "referenceDate": "2026-07-31",
            "window": "currentAndNextMonths",
            "summary": {"memorableDateCount": 1, "birthdayCount": 0},
            "entries": [
                {
                    "id": "1" * 32,
                    "kind": "memorableDate",
                    "displayName": "Годовщина",
                    "annualDate": {"day": 2, "month": 8, "year": 2020},
                    "period": "nextMonth",
                    "occurrenceYear": 2026,
                    "relatedPeople": [{"id": "2" * 32, "displayName": "Анна"}],
                },
            ],
        }
        self.use_case.get_calendar.assert_awaited_once_with(
            params=GetCalendarParams(
                reference_date=date(2026, 7, 31),
                window=CalendarWindow.CURRENT_AND_NEXT_MONTHS,
                author_username=TEST_USERNAME,
            ),
        )

    @pytest.mark.parametrize(
        ("reference_date", "window"),
        [
            ("2026-02-30", "month"),
            ("2026-02-01", "quarter"),
        ],
    )
    def test_rejects_invalid_query_parameters(self, reference_date: str, window: str) -> None:
        response = self.api.get_calendar(reference_date=reference_date, window=window)

        self.asserts.status(response=response, expected_status=codes.BAD_REQUEST)
        self.use_case.get_calendar.assert_not_called()

    def test_private_calendar_handlers_are_uncached(self) -> None:
        assert CalendarApiController.get_calendar.cache is False
