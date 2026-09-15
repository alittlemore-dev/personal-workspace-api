from datetime import date

import pytest

from core.knowledge.dates.schemas import KnowledgeDateValue
from core.knowledge.exceptions import InvalidKnowledgeDataError


class TestKnowledgeDatesDomain:
    def test_date_accepts_unknown_year_and_leap_day(self) -> None:
        value = KnowledgeDateValue(day=29, month=2, year=None)

        value.validate(today=date(2026, 7, 30))

    @pytest.mark.parametrize(
        ("day", "month", "year"),
        [
            (31, 4, None),
            (29, 2, 2025),
            (0, 1, None),
            (1, 13, None),
        ],
    )
    def test_date_rejects_impossible_combinations(
        self,
        day: int,
        month: int,
        year: int | None,
    ) -> None:
        with pytest.raises(InvalidKnowledgeDataError):
            KnowledgeDateValue(day=day, month=month, year=year)

    def test_date_rejects_future_start(self) -> None:
        value = KnowledgeDateValue(day=31, month=7, year=2026)

        with pytest.raises(InvalidKnowledgeDataError):
            value.validate(today=date(2026, 7, 30))
