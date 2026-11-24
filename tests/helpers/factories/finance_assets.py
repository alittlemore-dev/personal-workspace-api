from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import uuid4

from core.finance.assets.enums import AssetMovementKind, AssetPositionKind, AssetSource
from core.finance.assets.schemas import AssetMovement, AssetMovementDraft, AssetPosition
from core.finance.enums import FinanceCurrency


class FinanceAssetFactory:
    @staticmethod
    def position(
        id_: str = "cash",
        kind: AssetPositionKind = AssetPositionKind.CASH,
        currency: FinanceCurrency = FinanceCurrency.RUB,
    ) -> AssetPosition:
        return AssetPosition(
            id=id_,
            archived=False,
            name=id_,
            location_id="home",
            kind=kind,
            currency=currency,
            instrument="ABC" if kind.security else "",
            venue="M" if kind.security else "",
            annual_rate=None,
            matures_on=None,
        )

    @staticmethod
    def movement(
        kind: AssetMovementKind,
        day: date,
        position: str = "cash",
        *,
        amount: int | None = None,
        quantity: int | None = None,
        total_value: int | None = None,
        counter: str | None = None,
        rate: str | None = None,
    ) -> AssetMovement:
        created = datetime.combine(day, time(12), tzinfo=UTC)
        return AssetMovement(
            id=uuid4().hex,
            request_id=uuid4(),
            version=1,
            deleted=False,
            rate_set_id=rate,
            transaction_id=None,
            source=AssetSource.WEB,
            changed_at=created,
            created_at=created,
            draft=AssetMovementDraft(
                kind=kind,
                on_date=day,
                position_id=position,
                counter_position_id=counter,
                amount=Decimal(amount) if amount is not None else None,
                quantity=Decimal(quantity) if quantity is not None else None,
                total_value=Decimal(total_value) if total_value is not None else None,
                counter_amount=None,
                category_id=None,
                note="",
            ),
        )
