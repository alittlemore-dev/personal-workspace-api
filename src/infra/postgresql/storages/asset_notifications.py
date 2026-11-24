from dataclasses import asdict, dataclass
from datetime import date

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.finance.enums import FinanceCurrency
from core.finance.enums import FinanceEventKind as Kind
from core.notifications.enums import DeliveryStatus
from core.notifications.finance.assets import AssetNoticeStorage, AssetSubscriber
from core.notifications.finance.schemas import AssetFinanceEvent
from core.telegram.enums import TelegramConnectionState
from infra.postgresql.models.finance import FinanceMonthModel, FinanceTrackerModel
from infra.postgresql.models.finance_assets import AssetMovementModel
from infra.postgresql.models.finance_notifications import FinanceDeliveryModel, FinanceEventModel
from infra.postgresql.models.telegram import TelegramConnectionModel
from infra.postgresql.schemas.finance import AssetEventSourceSchema, NotificationPayloadSchema


@dataclass(kw_only=True)
class AssetDatabaseNoticeStorage(AssetNoticeStorage):
    session: AsyncSession

    async def subscribers(self, *, owner: str | None, goal: bool) -> list[AssetSubscriber]:
        c = TelegramConnectionModel
        query = (
            select(FinanceTrackerModel.owner_username, FinanceTrackerModel.time_zone)
            .join(
                c,
                c.owner_username == FinanceTrackerModel.owner_username,
            )
            .where(
                c.state == TelegramConnectionState.ACTIVE,
                c.notify_savings_goal_reached
                if goal
                else or_(c.notify_assets_month_summary, c.notify_deposit_maturity),
            )
            .distinct()
        )
        if owner is not None:
            query = query.where(FinanceTrackerModel.owner_username == owner)
        return [
            AssetSubscriber(owner=row[0], zone=row[1]) for row in await self.session.execute(query)
        ]

    async def currency(self, owner: str, month: date) -> FinanceCurrency | None:
        return await self.session.scalar(
            select(FinanceMonthModel.currency)
            .join(FinanceTrackerModel)
            .where(
                FinanceTrackerModel.owner_username == owner,
                FinanceMonthModel.period_start <= month,
            )
            .order_by(FinanceMonthModel.period_start.desc())
            .limit(1),
        )

    async def linked_payout(self, owner: str, transaction_id: str) -> bool:
        return (
            await self.session.scalar(
                select(AssetMovementModel.id)
                .join(FinanceTrackerModel)
                .where(
                    FinanceTrackerModel.owner_username == owner,
                    AssetMovementModel.transaction_id == transaction_id,
                ),
            )
            is not None
        )

    async def record(self, event: AssetFinanceEvent, *, active: bool) -> None:
        model = FinanceEventModel
        key = event.source.identifier
        if event.kind == Kind.DEPOSIT_MATURITY:
            key = f"{key}:{event.source.on_date}:7"
        if not active:
            await self.session.execute(
                update(model)
                .where(
                    model.owner_username == event.owner_username,
                    model.kind == event.kind,
                    model.source_key == key,
                    model.source_active,
                )
                .values(source_active=False, expires_at=event.created_at),
            )
            return
        statement = insert(model).values(
            owner_username=event.owner_username,
            kind=event.kind,
            source_key=key,
            source_active=True,
            payload=NotificationPayloadSchema(AssetEventSourceSchema(**asdict(event.source))),
            created_at=event.created_at,
            expires_at=event.expires_at,
            planned_at=None,
        )
        reactivate = ~model.source_active
        if event.kind in (Kind.MONTH_SUMMARY, Kind.DEPOSIT_MATURITY):
            reactivate = or_(reactivate, model.expires_at != event.expires_at)
        event_id = await self.session.scalar(
            statement.on_conflict_do_update(
                constraint="finance_event_source_once",
                where=reactivate,
                set_={
                    "source_active": True,
                    "expires_at": event.expires_at,
                    "planned_at": None,
                    "created_at": event.created_at,
                },
            ).returning(model.id),
        )
        if event_id is not None:
            await self.session.execute(
                update(FinanceDeliveryModel)
                .where(
                    FinanceDeliveryModel.event_id == event_id,
                    FinanceDeliveryModel.status.in_(
                        (DeliveryStatus.CANCELED, DeliveryStatus.EXPIRED),
                    ),
                )
                .values(
                    status=DeliveryStatus.PENDING,
                    attempts=0,
                    next_attempt_at=event.created_at,
                    claimed_until=None,
                    updated_at=event.created_at,
                ),
            )
