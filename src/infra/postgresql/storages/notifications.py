from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from core.notifications.enums import DeliveryStatus, ReminderKind
from core.notifications.schemas import (
    ReminderDelivery,
    ReminderDeliveryKey,
    ReminderRecipient,
    ReminderSource,
    ReminderWindow,
)
from core.notifications.storages import ReminderStorage
from core.telegram.enums import TelegramConnectionState
from infra.postgresql.models.knowledge.dates import (
    KnowledgeDateDetailsModel,
    KnowledgeDatePersonModel,
)
from infra.postgresql.models.knowledge.items import KnowledgeItemModel
from infra.postgresql.models.knowledge.people import PersonDetailsModel
from infra.postgresql.models.notifications import ReminderDeliveryModel
from infra.postgresql.models.telegram import TelegramConnectionModel


@dataclass(kw_only=True, slots=True)
class ReminderDatabaseStorage(ReminderStorage):
    session: AsyncSession

    async def list_recipients(self, *, after_id: str, limit: int) -> list[ReminderRecipient]:
        query = (
            select(TelegramConnectionModel)
            .where(
                TelegramConnectionModel.state == TelegramConnectionState.ACTIVE,
                TelegramConnectionModel.id > after_id,
                or_(
                    TelegramConnectionModel.notify_birthday.is_(True),
                    TelegramConnectionModel.notify_memorable_date.is_(True),
                ),
            )
            .order_by(TelegramConnectionModel.id)
            .limit(limit)
        )
        return [model.to_reminder_recipient() for model in await self.session.scalars(query)]

    async def get_recipient(self, *, connection_id: str) -> ReminderRecipient | None:
        model = await self.session.scalar(
            select(TelegramConnectionModel)
            .where(TelegramConnectionModel.id == connection_id)
            .execution_options(populate_existing=True),
        )
        if model is None or model.state != TelegramConnectionState.ACTIVE:
            return None
        return model.to_reminder_recipient()

    async def list_sources(
        self,
        *,
        owner_username: str,
        kind: ReminderKind,
        occurrence_date: date,
    ) -> list[ReminderSource]:
        if kind == ReminderKind.BIRTHDAY:
            birthday_query = (
                select(KnowledgeItemModel, PersonDetailsModel)
                .join(PersonDetailsModel, PersonDetailsModel.item_id == KnowledgeItemModel.id)
                .where(
                    KnowledgeItemModel.author_username == owner_username,
                    PersonDetailsModel.author_username == owner_username,
                    PersonDetailsModel.birthday_day == occurrence_date.day,
                    PersonDetailsModel.birthday_month == occurrence_date.month,
                    PersonDetailsModel.notifications_enabled.is_(True),
                    or_(
                        PersonDetailsModel.birthday_year.is_(None),
                        PersonDetailsModel.birthday_year <= occurrence_date.year,
                    ),
                )
                .execution_options(populate_existing=True)
            )
            rows = (await self.session.execute(birthday_query)).all()
            return [
                ReminderSource(
                    owner_username=owner_username,
                    item_id=item.id,
                    kind=kind,
                    title=item.display_name,
                    day=details.birthday_day,
                    month=details.birthday_month,
                    year=details.birthday_year,
                    description="",
                    related_people=(),
                    notifications_enabled=details.notifications_enabled,
                )
                for item, details in rows
            ]
        date_query = (
            select(KnowledgeItemModel, KnowledgeDateDetailsModel)
            .join(
                KnowledgeDateDetailsModel,
                KnowledgeDateDetailsModel.item_id == KnowledgeItemModel.id,
            )
            .where(
                KnowledgeItemModel.author_username == owner_username,
                KnowledgeDateDetailsModel.author_username == owner_username,
                KnowledgeDateDetailsModel.day == occurrence_date.day,
                KnowledgeDateDetailsModel.month == occurrence_date.month,
                KnowledgeDateDetailsModel.notifications_enabled.is_(True),
                or_(
                    KnowledgeDateDetailsModel.year.is_(None),
                    KnowledgeDateDetailsModel.year <= occurrence_date.year,
                ),
            )
            .execution_options(populate_existing=True)
        )
        date_rows = (await self.session.execute(date_query)).all()
        if not date_rows:
            return []
        date_ids = [item.id for item, _ in date_rows]
        people_query = (
            select(KnowledgeDatePersonModel.date_item_id, KnowledgeItemModel.display_name)
            .join(
                KnowledgeItemModel,
                and_(
                    KnowledgeItemModel.id == KnowledgeDatePersonModel.person_item_id,
                    KnowledgeItemModel.author_username == owner_username,
                ),
            )
            .where(
                KnowledgeDatePersonModel.author_username == owner_username,
                KnowledgeDatePersonModel.date_item_id.in_(date_ids),
            )
        )
        people: dict[str, list[str]] = {date_id: [] for date_id in date_ids}
        for date_id, name in (await self.session.execute(people_query)).all():
            people[date_id].append(name)
        return [
            ReminderSource(
                owner_username=owner_username,
                item_id=item.id,
                kind=kind,
                title=item.display_name,
                day=details.day,
                month=details.month,
                year=details.year,
                description=item.description,
                related_people=tuple(sorted(people[item.id], key=str.casefold)),
                notifications_enabled=details.notifications_enabled,
            )
            for item, details in date_rows
        ]

    @staticmethod
    def key_filter(key: ReminderDeliveryKey) -> ColumnElement[bool]:
        return and_(
            ReminderDeliveryModel.connection_id == key.connection_id,
            ReminderDeliveryModel.kind == key.kind,
            ReminderDeliveryModel.item_id == key.item_id,
            ReminderDeliveryModel.occurrence_date == key.occurrence_date,
            ReminderDeliveryModel.lead_days == key.lead_days,
        )

    async def plan(
        self,
        *,
        key: ReminderDeliveryKey,
        now: datetime,
        send_at: datetime,
        expires_at: datetime,
    ) -> bool:
        statement = insert(ReminderDeliveryModel).values(
            connection_id=key.connection_id,
            kind=key.kind,
            item_id=key.item_id,
            occurrence_date=key.occurrence_date,
            lead_days=key.lead_days,
            status=DeliveryStatus.PENDING,
            attempts=0,
            claimed_until=None,
            scheduled_at=send_at,
            next_attempt_at=send_at,
            expires_at=expires_at,
            updated_at=now,
            sent_at=None,
        )
        planned = statement.on_conflict_do_update(
            constraint="reminder_delivery_once_uniq",
            set_={
                "status": DeliveryStatus.PENDING,
                "attempts": 0,
                "claimed_until": None,
                "scheduled_at": send_at,
                "next_attempt_at": send_at,
                "expires_at": expires_at,
                "updated_at": now,
            },
            where=and_(
                ReminderDeliveryModel.status.in_(
                    (
                        DeliveryStatus.PENDING,
                        DeliveryStatus.RETRY,
                        DeliveryStatus.CANCELED,
                        DeliveryStatus.EXPIRED,
                    ),
                ),
                or_(
                    ReminderDeliveryModel.status.in_(
                        (DeliveryStatus.CANCELED, DeliveryStatus.EXPIRED),
                    ),
                    ReminderDeliveryModel.scheduled_at != send_at,
                    ReminderDeliveryModel.expires_at != expires_at,
                ),
            ),
        ).returning(ReminderDeliveryModel.id)
        return (await self.session.scalar(planned)) is not None

    async def claim_due(
        self,
        *,
        now: datetime,
        lease_until: datetime,
        max_attempts: int,
    ) -> ReminderDelivery | None:
        query = (
            select(ReminderDeliveryModel)
            .where(
                ReminderDeliveryModel.expires_at > now,
                ReminderDeliveryModel.attempts < max_attempts,
                or_(
                    and_(
                        ReminderDeliveryModel.status.in_(
                            (DeliveryStatus.PENDING, DeliveryStatus.RETRY),
                        ),
                        ReminderDeliveryModel.next_attempt_at <= now,
                    ),
                    and_(
                        ReminderDeliveryModel.status == DeliveryStatus.IN_PROGRESS,
                        ReminderDeliveryModel.claimed_until <= now,
                    ),
                ),
            )
            .order_by(ReminderDeliveryModel.next_attempt_at, ReminderDeliveryModel.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        model = await self.session.scalar(query)
        if model is None:
            return None
        model.status = DeliveryStatus.IN_PROGRESS
        model.attempts += 1
        model.claimed_until = lease_until
        model.updated_at = now
        await self.session.flush()
        return ReminderDelivery(
            key=ReminderDeliveryKey(
                connection_id=model.connection_id,
                kind=model.kind,
                item_id=model.item_id,
                occurrence_date=model.occurrence_date,
                lead_days=model.lead_days,
            ),
            attempts=model.attempts,
            scheduled_at=model.scheduled_at,
            expires_at=model.expires_at,
        )

    async def mark_done(self, *, key: ReminderDeliveryKey, now: datetime) -> None:
        await self.session.execute(
            update(ReminderDeliveryModel)
            .where(self.key_filter(key))
            .values(status=DeliveryStatus.DONE, sent_at=now, updated_at=now),
        )

    async def mark_canceled(self, *, key: ReminderDeliveryKey, now: datetime) -> None:
        await self.session.execute(
            update(ReminderDeliveryModel)
            .where(self.key_filter(key))
            .values(status=DeliveryStatus.CANCELED, updated_at=now),
        )

    async def mark_expired(self, *, key: ReminderDeliveryKey, now: datetime) -> None:
        await self.session.execute(
            update(ReminderDeliveryModel)
            .where(self.key_filter(key))
            .values(status=DeliveryStatus.EXPIRED, updated_at=now),
        )

    async def mark_failed(self, *, key: ReminderDeliveryKey, now: datetime) -> None:
        await self.session.execute(
            update(ReminderDeliveryModel)
            .where(self.key_filter(key))
            .values(status=DeliveryStatus.FAILED, updated_at=now),
        )

    async def mark_retry(
        self,
        *,
        key: ReminderDeliveryKey,
        now: datetime,
        next_attempt_at: datetime,
    ) -> None:
        await self.session.execute(
            update(ReminderDeliveryModel)
            .where(self.key_filter(key))
            .values(status=DeliveryStatus.RETRY, next_attempt_at=next_attempt_at, updated_at=now),
        )

    async def reschedule(
        self,
        *,
        key: ReminderDeliveryKey,
        now: datetime,
        send_at: datetime,
        expires_at: datetime,
    ) -> None:
        await self.session.execute(
            update(ReminderDeliveryModel)
            .where(self.key_filter(key), ReminderDeliveryModel.status == DeliveryStatus.IN_PROGRESS)
            .values(
                status=DeliveryStatus.PENDING,
                attempts=0,
                claimed_until=None,
                scheduled_at=send_at,
                next_attempt_at=send_at,
                expires_at=expires_at,
                updated_at=now,
            ),
        )

    async def defer_without_attempt(
        self,
        *,
        key: ReminderDeliveryKey,
        now: datetime,
        next_attempt_at: datetime,
    ) -> None:
        await self.session.execute(
            update(ReminderDeliveryModel)
            .where(self.key_filter(key), ReminderDeliveryModel.status == DeliveryStatus.IN_PROGRESS)
            .values(
                status=DeliveryStatus.RETRY,
                attempts=func.greatest(ReminderDeliveryModel.attempts - 1, 0),
                claimed_until=None,
                next_attempt_at=next_attempt_at,
                updated_at=now,
            ),
        )

    async def expire_and_prune(self, *, now: datetime, retention: timedelta) -> int:
        terminal = (
            DeliveryStatus.DONE,
            DeliveryStatus.CANCELED,
            DeliveryStatus.EXPIRED,
            DeliveryStatus.FAILED,
        )
        await self.session.execute(
            update(ReminderDeliveryModel)
            .where(
                ReminderDeliveryModel.expires_at <= now,
                ReminderDeliveryModel.status.not_in(terminal),
            )
            .values(status=DeliveryStatus.EXPIRED, updated_at=now),
        )
        deleted = await self.session.scalars(
            delete(ReminderDeliveryModel)
            .where(
                ReminderDeliveryModel.status.in_(terminal),
                ReminderDeliveryModel.updated_at < now - retention,
            )
            .returning(ReminderDeliveryModel.id),
        )
        return len(deleted.all())

    async def get_current(
        self,
        *,
        key: ReminderDeliveryKey,
        now: datetime,
        local_send_time: time,
        time_zone: ZoneInfo,
    ) -> tuple[ReminderRecipient, ReminderSource] | None:
        model = await self.session.scalar(
            select(TelegramConnectionModel)
            .where(TelegramConnectionModel.id == key.connection_id)
            .execution_options(populate_existing=True),
        )
        if model is None or model.state != TelegramConnectionState.ACTIVE:
            return None
        current = model.to_reminder_recipient()
        window = ReminderWindow.for_account(
            now=now,
            time_zone=time_zone,
            local_send_time=local_send_time,
        )
        if (
            not current.subscribes_to(kind=key.kind)
            or not window.eligible
            or window.local_date + timedelta(days=key.lead_days) != key.occurrence_date
        ):
            return None
        sources = await self.list_sources(
            owner_username=current.owner_username,
            kind=key.kind,
            occurrence_date=key.occurrence_date,
        )
        for current_source in sources:
            if current_source.item_id == key.item_id:
                return current, current_source
        return None
