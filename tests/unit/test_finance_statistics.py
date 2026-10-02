from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from core.finance.enums import FinanceCurrency, FinanceKind, FinanceStatisticsPeriod
from core.finance.exceptions import FinanceConflictError
from core.finance.schemas import Amount, FinanceStatisticsFact, FinanceStatisticsWindow
from core.finance.services import FinanceStatisticsService
from tests.helpers.factories.core import CoreFactoryHelper


@pytest.mark.parametrize(
    ("period", "days"),
    [
        (FinanceStatisticsPeriod.LAST_7_DAYS, 7),
        (FinanceStatisticsPeriod.LAST_30_DAYS, 30),
        (FinanceStatisticsPeriod.LAST_365_DAYS, 365),
    ],
)
def test_rolling_periods_include_today_and_compare_disjoint_previous_days(
    period: FinanceStatisticsPeriod,
    days: int,
):
    current, previous = FinanceStatisticsWindow.for_period(
        period,
        datetime(2026, 10, 2, 23, tzinfo=UTC),
        ZoneInfo("Asia/Yerevan"),
    )
    assert current.end.date() == date(2026, 10, 4)
    assert (current.end.date() - current.start.date()).days == days
    assert previous.end == current.start
    assert (previous.end.date() - previous.start.date()).days == days


@pytest.mark.parametrize(("day", "hours"), [(date(2026, 3, 29), 23), (date(2026, 10, 25), 25)])
def test_hourly_timeline_covers_daylight_saving_days_once(day: date, hours: int):
    current, _ = FinanceStatisticsWindow.for_period(
        FinanceStatisticsPeriod.TODAY,
        datetime.combine(day, datetime.min.time(), ZoneInfo("Europe/Berlin")),
        ZoneInfo("Europe/Berlin"),
    )
    points = FinanceStatisticsService().timeline(
        window=current,
        facts=[],
        currency=FinanceCurrency.USD,
    )
    assert len(points) == hours
    assert points[0].start == current.start
    assert points[-1].end == current.end
    assert all(
        (p.end.astimezone(UTC) - p.start.astimezone(UTC)).total_seconds() == 3600 for p in points
    )


def test_month_categories_follow_stable_identity_and_exclude_end_boundary():
    current, previous = FinanceStatisticsWindow.for_period(
        FinanceStatisticsPeriod.THIS_YEAR,
        datetime(2026, 10, 2, tzinfo=UTC),
        ZoneInfo("UTC"),
    )
    facts = [
        FinanceStatisticsFact(
            currency=FinanceCurrency.USD,
            occurred_at=datetime(2026, month, 2, tzinfo=UTC),
            kind=FinanceKind.INCOME,
            amount=Amount(amount),
            category_id=category_id,
            category_name=name,
            category_period=date(2026, month, 1),
        )
        for month, amount, category_id, name in [
            (1, "10.125", "salary", "Old name"),
            (2, "10.125", "salary", "New name"),
            (3, "5", "", ""),
        ]
    ]
    facts.append(
        FinanceStatisticsFact(
            currency=FinanceCurrency.USD,
            occurred_at=current.end,
            kind=FinanceKind.INCOME,
            amount=Amount(1000),
            category_id="salary",
            category_name="Future",
            category_period=date(2027, 1, 1),
        ),
    )
    result = FinanceStatisticsService().breakdown(
        kind=FinanceKind.INCOME,
        currency=FinanceCurrency.USD,
        window=current,
        previous_window=previous,
        facts=facts,
    )
    assert result.actual == Amount("25.25")
    assert result.previous == 0
    assert result.change_percent is None
    assert len(result.timeline) == 12
    assert result.categories[0].name == "New name"
    assert result.categories[0].amount == Amount("20.25")
    assert result.categories[1].id == ""


def test_calendar_month_compares_entire_previous_month_including_leap_day():
    current, previous = FinanceStatisticsWindow.for_period(
        FinanceStatisticsPeriod.THIS_MONTH,
        datetime(2024, 3, 2, tzinfo=UTC),
        ZoneInfo("UTC"),
    )
    assert previous.start.date() == date(2024, 2, 1)
    assert previous.end.date() == date(2024, 3, 1)
    facts = [
        FinanceStatisticsFact(
            currency=FinanceCurrency.USD,
            occurred_at=datetime(2024, month, day, tzinfo=UTC),
            kind=FinanceKind.EXPENSE,
            amount=Amount(amount),
            category_id="food",
            category_name="Food",
            category_period=date(2024, month, 1),
        )
        for month, day, amount in [(2, 29, 20), (3, 31, 30)]
    ]
    result = FinanceStatisticsService().breakdown(
        kind=FinanceKind.EXPENSE,
        currency=FinanceCurrency.AMD,
        window=current,
        previous_window=previous,
        facts=facts,
    )
    assert (result.actual, result.previous, result.change, result.change_percent) == (
        Amount(30),
        Amount(20),
        Amount(10),
        Decimal(50),
    )
    assert result.timeline[-1].amount == 30


@pytest.mark.parametrize(
    ("created", "editable"),
    [
        (datetime(2026, 9, 30, 19, 59, tzinfo=UTC), False),
        (datetime(2026, 9, 30, 20, 0, tzinfo=UTC), True),
    ],
)
def test_late_edit_permission_uses_creation_month_in_tracker_time_zone(
    created: datetime,
    editable: bool,
):
    month = CoreFactoryHelper.finance_month(
        period_start=date(2026, 9, 1),
        time_zone=ZoneInfo("Asia/Yerevan"),
    )
    transaction = replace(CoreFactoryHelper.finance_transaction(), created_at=created)
    now = datetime(2026, 10, 2, tzinfo=UTC)
    if editable:
        transaction.check_writable(month, now)
    else:
        with pytest.raises(FinanceConflictError):
            transaction.check_writable(month, now)
