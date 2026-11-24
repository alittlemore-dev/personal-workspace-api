from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from core.finance.assets.enums import AssetMovementKind as Kind
from core.finance.assets.enums import AssetPositionKind
from core.finance.assets.valuation import AssetLedger, AssetRate, AssetRates, DailyPrice
from core.finance.enums import FinanceCurrency
from core.finance.exceptions import InvalidFinanceDataError
from tests.helpers.factories.finance_assets import FinanceAssetFactory as Factory


@pytest.mark.parametrize(
    ("kind", "amount", "currency"),
    [
        (Kind.DEPOSIT_EXTERNAL, Decimal(2), None),
        (Kind.WITHDRAW_EXTERNAL, None, FinanceCurrency.USD),
        (Kind.DEPOSIT_EXTERNAL, Decimal("0.5"), FinanceCurrency.AMD),
        (Kind.CONTRIBUTION, Decimal(2), FinanceCurrency.USD),
    ],
)
def test_asset_operation_validates_entered_currency_pair(
    kind: Kind,
    amount: Decimal | None,
    currency: FinanceCurrency | None,
) -> None:
    original = Factory.movement(kind, date(2026, 3, 31), amount=10)
    draft = replace(original.draft, entered_currency=currency, entered_amount=amount)
    with pytest.raises(InvalidFinanceDataError):
        draft.validate(Factory.position(), None)


@pytest.mark.parametrize(
    ("price", "includes_coupon", "face", "expected"),
    [
        ("98", False, "1000", "992"),
        ("99.2", True, "1000", "992"),
        ("98", False, None, None),
    ],
)
def test_bond_quote_and_completed_session(
    price: str,
    includes_coupon: bool,
    face: str | None,
    expected: str | None,
) -> None:
    friday = date(2026, 3, 27)
    quote = DailyPrice(
        on_date=friday,
        source="provider",
        price=Decimal(price),
        percent_of_face=True,
        face_value=Decimal(face) if face else None,
        includes_coupon=includes_coupon,
        accrued_coupon=Decimal(12),
    )
    assert quote.unit_price == (Decimal(expected) if expected else None)
    assert not quote.stale(last_completed_session=friday)
    assert quote.stale(last_completed_session=date(2026, 3, 30))


def test_position_observation_is_whole_and_future_valuation_cannot_change_history() -> None:
    march = date(2026, 3, 31)
    movements = [
        Factory.movement(Kind.CONTRIBUTION, date(2026, 3, 1), amount=10000),
        Factory.movement(
            Kind.BUY,
            date(2026, 3, 2),
            "stock",
            counter="cash",
            amount=6000,
            quantity=3,
        ),
        Factory.movement(Kind.WITHDRAWAL, date(2026, 3, 3), amount=4000),
        Factory.movement(Kind.VALUATION, march, "stock", total_value=6500),
        Factory.movement(Kind.VALUATION, date(2026, 4, 1), "stock", total_value=9000),
    ]
    ledger = AssetLedger(
        positions=[Factory.position(), Factory.position("stock", AssetPositionKind.STOCK)],
        movements=movements,
        rates=AssetRates(ordered=[]),
    )
    value = ledger.evaluate(march, FinanceCurrency.RUB)
    assert value.complete
    assert value.known_value == 6500
    assert value.positions[1].quantity == 3
    assert value.positions[1].price_source == "manual"


def test_only_dated_statement_positions_and_as_of_rates_are_known() -> None:
    march = date(2026, 3, 31)
    rub = FinanceCurrency.RUB
    usd = FinanceCurrency.USD
    ledger = AssetLedger(
        positions=[
            Factory.position(currency=usd),
            Factory.position("stock", AssetPositionKind.STOCK),
        ],
        movements=[Factory.movement(Kind.STATEMENT, march, amount=20)],
        rates=AssetRates(
            ordered=[
                AssetRate(
                    id="march",
                    source="cbr",
                    on_date=march,
                    rates={usd: Decimal(80), rub: Decimal(1)},
                ),
                AssetRate(
                    id="april",
                    source="cbr",
                    on_date=date(2026, 4, 1),
                    rates={usd: Decimal(90), rub: Decimal(1)},
                ),
            ],
        ),
    )
    value = ledger.evaluate(march, rub)
    assert value.known_value == 1600
    assert not value.complete
    assert value.positions[1].quantity is None
    assert value.positions[0].rate_date == march
    assert all(row.value is None for row in ledger.evaluate(date(2026, 4, 2), rub).positions)
    missing = ledger.evaluate(march, FinanceCurrency.EUR)
    assert missing.positions[0].missing_rate
    assert not missing.complete


def test_other_position_uses_dated_whole_values_without_units() -> None:
    other = Factory.position("contract", AssetPositionKind.OTHER)
    start, statement, mark, reconcile = (date(2026, 3, day) for day in (2, 1, 3, 4))
    movements = [
        Factory.movement(Kind.STATEMENT, statement, other.id, amount=80),
        Factory.movement(Kind.OPENING_EXTERNAL, start, other.id, amount=100),
        Factory.movement(Kind.VALUATION, mark, other.id, total_value=125),
        Factory.movement(Kind.RECONCILE, reconcile, other.id, amount=130),
        Factory.movement(Kind.PAYOUT_TO_BUDGET, reconcile, other.id, amount=5),
    ]
    for movement in movements:
        movement.draft.validate(other, None)
    ledger = AssetLedger(positions=[other], rates=AssetRates(ordered=[]), movements=movements)
    before = ledger.evaluate(date(2026, 2, 28), FinanceCurrency.RUB)
    assert not before.complete
    for day, amount, source in (
        (statement, 80, "statement"),
        (start, 100, "opening"),
        (mark, 125, "manual"),
        (reconcile, 130, "statement"),
    ):
        row = ledger.evaluate(day, FinanceCurrency.RUB).positions[0]
        assert row.original_value == amount
        assert row.quantity is None
        assert row.price_date == day
        assert row.price_source == source
    cash = Factory.position()
    with pytest.raises(InvalidFinanceDataError):
        Factory.movement(Kind.WITHDRAWAL, start, other.id, amount=5).draft.validate(other, None)
    transfer = Factory.movement(Kind.TRANSFER, start, cash.id, amount=5, counter=other.id)
    with pytest.raises(InvalidFinanceDataError):
        transfer.draft.validate(cash, other)
    with pytest.raises(InvalidFinanceDataError):
        replace(other, instrument="ABC", venue="XYZ").validate()


def test_cash_movements_use_the_last_confirmed_monetary_balance() -> None:
    ledger = AssetLedger(
        positions=[Factory.position()],
        rates=AssetRates(ordered=[]),
        movements=[
            Factory.movement(Kind.OPENING_EXTERNAL, date(2026, 3, 1), amount=100),
            Factory.movement(Kind.VALUATION, date(2026, 3, 2), total_value=110),
            Factory.movement(Kind.WITHDRAWAL, date(2026, 3, 3), amount=50),
        ],
    )
    assert ledger.evaluate(date(2026, 3, 3), FinanceCurrency.RUB).known_value == 60
