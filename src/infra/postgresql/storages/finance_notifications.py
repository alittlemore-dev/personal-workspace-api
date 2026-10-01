from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.finance.event_dispatchers import FinanceEventDispatcher
from core.finance.schemas import FinanceEvent
from core.notifications.enums import DeliveryStatus
from core.notifications.finance import FinanceDelivery, FinanceDeliveryStorage
from core.telegram.enums import TelegramConnectionState
from infra.postgresql.models.finance_notifications import FinanceDeliveryModel, FinanceEventModel
from infra.postgresql.models.telegram import TelegramConnectionModel
from infra.postgresql.schemas.finance import FinanceEventPayloadSchema


@dataclass(kw_only=True, slots=True)
class FinanceDatabaseEventDispatcher(FinanceEventDispatcher):
    session: AsyncSession

    async def publish(self, *, event: FinanceEvent) -> None:
        self.session.add(
            FinanceEventModel(
                owner_username=event.owner_username,
                kind=event.kind,
                payload=FinanceEventPayloadSchema.model_validate(event.payload),
                created_at=event.created_at,
                expires_at=event.expires_at,
                planned_at=None,
            ),
        )
        await self.session.flush()


@dataclass(kw_only=True, slots=True)
class FinanceDatabaseDeliveryStorage(FinanceDeliveryStorage):
    session: AsyncSession

    async def plan(self, *, now: datetime, limit: int) -> int:
        events = await self.session.scalars(
            select(FinanceEventModel)
            .where(FinanceEventModel.planned_at.is_(None))
            .order_by(FinanceEventModel.created_at, FinanceEventModel.id)
            .limit(limit)
            .with_for_update(skip_locked=True),
        )
        count = 0
        for event in events:
            if event.expires_at > now:
                connection_ids = await self.session.scalars(
                    select(TelegramConnectionModel.id).where(
                        TelegramConnectionModel.owner_username == event.owner_username,
                        TelegramConnectionModel.state == TelegramConnectionState.ACTIVE,
                        TelegramConnectionModel.connected_at <= event.created_at,
                    ),
                )
                for connection_id in connection_ids:
                    await self.session.execute(
                        insert(FinanceDeliveryModel)
                        .values(
                            event_id=event.id,
                            connection_id=connection_id,
                            kind=event.kind,
                            status=DeliveryStatus.PENDING,
                            attempts=0,
                            claimed_until=None,
                            next_attempt_at=now,
                            updated_at=now,
                        )
                        .on_conflict_do_nothing(
                            constraint="finance_delivery_once",
                        ),
                    )
                    count += 1
            event.planned_at = now
        await self.session.flush()
        return count

    async def claim(
        self,
        *,
        now: datetime,
        lease_until: datetime,
        max_attempts: int,
    ) -> FinanceDelivery | None:
        await self.session.execute(
            update(FinanceDeliveryModel)
            .where(
                FinanceDeliveryModel.status.in_(
                    (DeliveryStatus.PENDING, DeliveryStatus.RETRY, DeliveryStatus.IN_PROGRESS),
                ),
                FinanceDeliveryModel.attempts >= max_attempts,
                or_(
                    FinanceDeliveryModel.claimed_until.is_(None),
                    FinanceDeliveryModel.claimed_until <= now,
                ),
            )
            .values(status=DeliveryStatus.FAILED, updated_at=now, claimed_until=None),
        )
        row = (
            await self.session.execute(
                select(FinanceDeliveryModel, FinanceEventModel)
                .join(FinanceEventModel)
                .where(
                    FinanceDeliveryModel.status.in_(
                        (DeliveryStatus.PENDING, DeliveryStatus.RETRY, DeliveryStatus.IN_PROGRESS),
                    ),
                    FinanceDeliveryModel.next_attempt_at <= now,
                    or_(
                        FinanceDeliveryModel.claimed_until.is_(None),
                        FinanceDeliveryModel.claimed_until <= now,
                    ),
                    FinanceDeliveryModel.attempts < max_attempts,
                )
                .order_by(FinanceDeliveryModel.next_attempt_at, FinanceDeliveryModel.id)
                .limit(1)
                .with_for_update(skip_locked=True, of=FinanceDeliveryModel)
                .execution_options(populate_existing=True),
            )
        ).first()
        if row is None:
            return None
        delivery, event = row
        delivery.status = DeliveryStatus.IN_PROGRESS
        delivery.attempts += 1
        delivery.claimed_until = lease_until
        delivery.updated_at = now
        connection = await self.session.scalar(
            select(TelegramConnectionModel)
            .where(
                TelegramConnectionModel.id == delivery.connection_id,
                TelegramConnectionModel.owner_username == event.owner_username,
                TelegramConnectionModel.state == TelegramConnectionState.ACTIVE,
            )
            .execution_options(populate_existing=True),
        )
        result = FinanceDelivery(
            id=delivery.id,
            attempts=delivery.attempts,
            event=FinanceEvent(
                owner_username=event.owner_username,
                kind=event.kind,
                payload=event.payload.to_domain_schema(),
                created_at=event.created_at,
                expires_at=event.expires_at,
            ),
            connection=connection.to_domain_schema() if connection is not None else None,
        )
        await self.session.flush()
        return result

    async def refresh(self, *, delivery: FinanceDelivery, now: datetime) -> FinanceDelivery | None:
        claimed = await self.session.scalar(
            select(FinanceDeliveryModel)
            .where(
                FinanceDeliveryModel.id == delivery.id,
                FinanceDeliveryModel.status == DeliveryStatus.IN_PROGRESS,
                FinanceDeliveryModel.attempts == delivery.attempts,
                FinanceDeliveryModel.claimed_until > now,
            )
            .execution_options(populate_existing=True),
        )
        if claimed is None:
            return None
        connection = await self.session.scalar(
            select(TelegramConnectionModel)
            .where(
                TelegramConnectionModel.id == claimed.connection_id,
                TelegramConnectionModel.owner_username == delivery.event.owner_username,
                TelegramConnectionModel.state == TelegramConnectionState.ACTIVE,
            )
            .execution_options(populate_existing=True),
        )
        return replace(
            delivery,
            connection=connection.to_domain_schema() if connection is not None else None,
        )

    async def finish(
        self,
        *,
        delivery: FinanceDelivery,
        status: DeliveryStatus,
        now: datetime,
        next_attempt_at: datetime,
    ) -> None:
        await self.session.execute(
            update(FinanceDeliveryModel)
            .where(
                FinanceDeliveryModel.id == delivery.id,
                FinanceDeliveryModel.status == DeliveryStatus.IN_PROGRESS,
                FinanceDeliveryModel.attempts == delivery.attempts,
            )
            .values(
                status=status,
                updated_at=now,
                claimed_until=None,
                next_attempt_at=next_attempt_at,
            ),
        )

    async def prune(self, *, now: datetime, retention: timedelta) -> int:
        expired = select(FinanceEventModel.id).where(FinanceEventModel.expires_at <= now)
        await self.session.execute(
            update(FinanceDeliveryModel)
            .where(
                FinanceDeliveryModel.event_id.in_(expired),
                FinanceDeliveryModel.status.in_(
                    (DeliveryStatus.PENDING, DeliveryStatus.RETRY, DeliveryStatus.IN_PROGRESS),
                ),
                or_(
                    FinanceDeliveryModel.claimed_until.is_(None),
                    FinanceDeliveryModel.claimed_until <= now,
                ),
            )
            .values(status=DeliveryStatus.EXPIRED, updated_at=now, claimed_until=None),
        )
        await self.session.execute(
            delete(FinanceDeliveryModel).where(
                FinanceDeliveryModel.status.in_(
                    (
                        DeliveryStatus.DONE,
                        DeliveryStatus.CANCELED,
                        DeliveryStatus.EXPIRED,
                        DeliveryStatus.FAILED,
                    ),
                ),
                FinanceDeliveryModel.updated_at < now - retention,
            ),
        )
        removed = await self.session.scalars(
            delete(FinanceEventModel)
            .where(
                FinanceEventModel.expires_at < now - retention,
                ~select(FinanceDeliveryModel.id)
                .where(FinanceDeliveryModel.event_id == FinanceEventModel.id)
                .exists(),
            )
            .returning(FinanceEventModel.id),
        )
        return len(list(removed))
