from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

from core.finance.assets.enums import AssetMovementKind as Kind
from core.finance.assets.enums import AssetPositionKind
from core.finance.assets.goals import AssetGoal
from core.finance.assets.reports import AssetIncome, AssetReportCalculator, AssetReportFacts
from core.finance.assets.valuation import AssetLedger, AssetRate, AssetRates
from core.finance.enums import FinanceCurrency
from core.notifications.finance.assets import AssetNotificationService
from tests.helpers.factories.finance_assets import FinanceAssetFactory as Factory


def test_annual_goal_weights_by_income_and_counts_only_fully_observed_months() -> None:
    january, february = date(2026, 1, 1), date(2026, 2, 1)
    calculator = AssetReportCalculator(
        currency=FinanceCurrency.RUB,
        today=date(2026, 3, 1),
        ledger=AssetLedger(
            positions=[Factory.position()],
            rates=AssetRates(ordered=[]),
            movements=[
                Factory.movement(Kind.CONTRIBUTION, january, amount=5000),
                Factory.movement(Kind.CONTRIBUTION, february, amount=40000),
            ],
        ),
        facts=AssetReportFacts(
            zone=ZoneInfo("UTC"),
            goals=[
                AssetGoal(month=january, percent=Decimal(10), all_income=True, category_ids=()),
                AssetGoal(
                    month=february,
                    percent=Decimal(20),
                    all_income=False,
                    category_ids=("salary",),
                ),
            ],
            incomes=[
                AssetIncome(on_date=january, category_id=None, amount=Decimal(100000)),
                AssetIncome(on_date=february, category_id="salary", amount=Decimal(200000)),
                AssetIncome(on_date=february, category_id=None, amount=Decimal(100)),
            ],
        ),
    )
    report = calculator.build(january, date(2026, 2, 28))
    assert report.net_savings == 45000
    assert report.income == 300000
    assert report.actual_percent == 15
    assert report.target_amount == 50000
    assert report.achieved_months == 1
    assert report.eligible_months == 2
    assert report.revaluation == 0
    partial = calculator.build(date(2026, 1, 2), date(2026, 2, 12))
    assert partial.net_savings == 40000
    assert partial.achieved_months == 0
    assert partial.eligible_months == 0
    assert partial.forecast.observation_months == [january]


def test_forecast_uses_three_completed_months_and_current_income_selection() -> None:
    months = [date(2026, month, 1) for month in range(1, 4)]
    calculator = AssetReportCalculator(
        currency=FinanceCurrency.RUB,
        today=date(2026, 4, 15),
        ledger=AssetLedger(
            positions=[Factory.position()],
            rates=AssetRates(ordered=[]),
            movements=[Factory.movement(Kind.CONTRIBUTION, day, amount=7000) for day in months],
        ),
        facts=AssetReportFacts(
            zone=ZoneInfo("UTC"),
            goals=[
                AssetGoal(
                    month=date(2026, 4, 1),
                    percent=Decimal(10),
                    all_income=False,
                    category_ids=("salary",),
                ),
            ],
            incomes=[
                AssetIncome(on_date=day, category_id="salary", amount=Decimal(100000))
                for day in months
            ]
            + [AssetIncome(on_date=months[0], category_id=None, amount=Decimal(1000))],
        ),
    )
    forecast = calculator.build(date(2026, 4, 1), date(2026, 4, 30)).forecast
    assert forecast.observation_months == months
    assert forecast.monthly_actual == 7000
    assert forecast.monthly_target == 10000
    end = forecast.points[-1]
    assert end.target is not None
    assert end.target - end.actual == 36000


def test_partial_history_negative_savings_and_unknown_price_preserve_known_amounts() -> None:
    start = date(2026, 3, 15)
    calculator = AssetReportCalculator(
        currency=FinanceCurrency.RUB,
        today=date(2026, 3, 31),
        ledger=AssetLedger(
            positions=[Factory.position(), Factory.position("stock", AssetPositionKind.STOCK)],
            movements=[
                Factory.movement(Kind.OPENING_EXTERNAL, start, amount=101000),
                Factory.movement(Kind.OPENING_EXTERNAL, start, "stock", quantity=15),
                Factory.movement(Kind.WITHDRAWAL, date(2026, 3, 16), amount=1000),
            ],
            rates=AssetRates(ordered=[]),
        ),
        facts=AssetReportFacts(zone=ZoneInfo("UTC"), goals=[], incomes=[]),
    )
    report = calculator.build(date(2026, 3, 1), date(2026, 3, 31))
    assert report.coverage_start == start
    assert report.closing.known_value == 100000
    assert report.net_savings == -1000
    assert report.non_interest_percent is None
    assert not report.closing.complete
    assert report.actual_percent is None
    assert not report.months[0].full
    assert report.forecast.available_on == date(2026, 5, 1)
    assert report.forecast.points == []
    calculator.facts.incomes.append(
        AssetIncome(on_date=start, category_id=None, amount=Decimal(5000)),
    )
    assert calculator.build(start, date(2026, 3, 31)).actual_percent == -20


def test_historical_statement_does_not_qualify_a_partial_month_for_goal_delivery() -> None:
    first, tracking = date(2026, 3, 1), date(2026, 3, 12)
    calculator = AssetReportCalculator(
        currency=FinanceCurrency.RUB,
        today=date(2026, 3, 20),
        ledger=AssetLedger(
            positions=[Factory.position()],
            rates=AssetRates(ordered=[]),
            movements=[
                Factory.movement(Kind.STATEMENT, first, amount=100),
                Factory.movement(Kind.CONTRIBUTION, tracking, amount=100),
            ],
        ),
        facts=AssetReportFacts(
            zone=ZoneInfo("UTC"),
            incomes=[AssetIncome(on_date=tracking, category_id=None, amount=Decimal(1000))],
            goals=[AssetGoal(month=first, percent=Decimal(10), all_income=True, category_ids=())],
        ),
    )
    report = calculator.build(first, date(2026, 3, 31))
    assert report.coverage_start == first
    assert report.net_savings == report.target_amount == 100
    assert not AssetNotificationService.reached(report)


def test_pretracking_statement_does_not_create_a_spurious_price_change_at_opening() -> None:
    march = date(2026, 3, 1)
    report = AssetReportCalculator(
        currency=FinanceCurrency.RUB,
        today=date(2026, 4, 1),
        ledger=AssetLedger(
            positions=[Factory.position()],
            movements=[
                Factory.movement(Kind.STATEMENT, date(2026, 2, 28), amount=80),
                Factory.movement(Kind.OPENING_EXTERNAL, march, amount=100),
            ],
            rates=AssetRates(ordered=[]),
        ),
        facts=AssetReportFacts(zone=ZoneInfo("UTC"), goals=[], incomes=[]),
    ).build(march, date(2026, 3, 31))
    assert report.opening.known_value == 80
    assert report.closing.known_value == 100
    assert report.initial_assets == 100
    assert report.revaluation is None


def test_direct_purchases_share_monthly_rounding_with_contributions() -> None:
    usd, amd = FinanceCurrency.USD, FinanceCurrency.AMD
    months = [date(2026, month, 1) for month in range(1, 5)]
    rate = AssetRate(
        id="rate",
        source="cbr",
        on_date=months[0],
        rates={usd: Decimal("384.4"), amd: Decimal(1)},
    )
    ledger = AssetLedger(
        positions=[
            Factory.position(currency=usd),
            Factory.position("stock", AssetPositionKind.STOCK, usd),
        ],
        rates=AssetRates(ordered=[rate]),
        movements=[
            Factory.movement(Kind.CONTRIBUTION, month, amount=1, rate=rate.id) for month in months
        ]
        + [
            Factory.movement(
                Kind.BUY_FROM_BUDGET,
                months[0],
                "stock",
                amount=1,
                quantity=1,
                rate=rate.id,
            ),
        ],
    )
    report = AssetReportCalculator(
        currency=amd,
        today=date(2026, 5, 1),
        ledger=ledger,
        facts=AssetReportFacts(zone=ZoneInfo("UTC"), goals=[], incomes=[]),
    ).build(months[0], date(2026, 4, 30))
    assert [m.net_savings for m in report.months] == [Decimal(769), *[Decimal(384)] * 3]
    assert report.deposits == report.net_savings == 1921
