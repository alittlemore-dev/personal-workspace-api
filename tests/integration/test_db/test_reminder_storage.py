import asyncio
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.i18n.enums import LanguageEnum
from core.knowledge.dates.schemas import KnowledgeDateDetails, KnowledgeDateValue
from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.items.schemas import KnowledgeItemCreateParams
from core.knowledge.people.schemas import PersonBirthday, PersonDetails
from core.notifications.enums import DeliveryStatus, ReminderKind
from core.notifications.schemas import ReminderDeliveryKey
from core.telegram.enums import TelegramConnectionState
from core.telegram.schemas import TelegramConnectionSettings, TelegramParticipant
from infra.postgresql.models.knowledge.dates import KnowledgeDateDetailsModel
from infra.postgresql.models.notifications import ReminderDeliveryModel
from infra.postgresql.storages.knowledge.dates import KnowledgeDatesDatabaseStorage
from infra.postgresql.storages.knowledge.items import KnowledgeItemsDatabaseStorage
from infra.postgresql.storages.knowledge.people import PeopleDatabaseStorage
from infra.postgresql.storages.notifications import ReminderDatabaseStorage
from infra.postgresql.storages.telegram import TelegramDatabaseStorage


async def test_concurrent_planners_create_one_pending_delivery_and_claim_once(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime(2026, 12, 25, 9, tzinfo=UTC)
    key = ReminderDeliveryKey(
        connection_id="c" * 32,
        kind=ReminderKind.BIRTHDAY,
        item_id="i" * 32,
        occurrence_date=date(2027, 1, 1),
        lead_days=7,
    )

    async def plan() -> bool:
        async with session_maker() as db:
            storage = ReminderDatabaseStorage(session=db)
            acquired = await storage.plan(
                key=key,
                now=now,
                send_at=now,
                expires_at=now + timedelta(hours=15),
            )
            await db.commit()
            return acquired

    assert sorted(await asyncio.gather(plan(), plan())) == [False, True]
    count = await session.scalar(select(func.count()).select_from(ReminderDeliveryModel))
    assert count == 1
    delivery = await session.scalar(select(ReminderDeliveryModel))
    assert delivery is not None
    assert delivery.status == DeliveryStatus.PENDING
    assert delivery.attempts == 0

    retry_at = now + timedelta(minutes=15)
    storage = ReminderDatabaseStorage(session=session)
    first_claim = await storage.claim_due(
        now=now,
        lease_until=now + timedelta(minutes=5),
        max_attempts=3,
    )
    assert first_claim is not None
    assert first_claim.key == key
    assert first_claim.attempts == 1
    await session.commit()
    assert (
        await storage.claim_due(
            now=now,
            lease_until=now + timedelta(minutes=5),
            max_attempts=3,
        )
        is None
    )
    await storage.mark_retry(key=key, now=now, next_attempt_at=retry_at)
    await session.commit()
    assert (
        await storage.claim_due(
            now=retry_at - timedelta(seconds=1),
            lease_until=retry_at + timedelta(minutes=5),
            max_attempts=3,
        )
        is None
    )
    second_claim = await storage.claim_due(
        now=retry_at,
        lease_until=retry_at + timedelta(minutes=5),
        max_attempts=3,
    )
    assert second_claim is not None
    assert second_claim.attempts == 2


async def test_zone_change_replans_unsent_delivery_and_preserves_done_dedup(
    session: AsyncSession,
) -> None:
    now = datetime(2026, 12, 25, 8, tzinfo=UTC)
    key = ReminderDeliveryKey(
        connection_id="c" * 32,
        kind=ReminderKind.BIRTHDAY,
        item_id="i" * 32,
        occurrence_date=date(2027, 1, 1),
        lead_days=7,
    )
    storage = ReminderDatabaseStorage(session=session)
    first_send = now + timedelta(hours=1)
    shifted_send = now + timedelta(hours=6)
    first_expiry = now + timedelta(hours=16)
    shifted_expiry = now + timedelta(hours=21)

    assert await storage.plan(key=key, now=now, send_at=first_send, expires_at=first_expiry)
    assert not await storage.plan(key=key, now=now, send_at=first_send, expires_at=first_expiry)
    assert await storage.plan(key=key, now=now, send_at=shifted_send, expires_at=shifted_expiry)
    await session.commit()
    model = await session.scalar(select(ReminderDeliveryModel))
    assert model is not None
    assert model.scheduled_at == shifted_send
    assert model.next_attempt_at == shifted_send
    assert model.expires_at == shifted_expiry

    await storage.mark_canceled(key=key, now=now)
    assert await storage.plan(key=key, now=now, send_at=shifted_send, expires_at=shifted_expiry)
    await session.commit()
    await session.refresh(model)
    assert model.status == DeliveryStatus.PENDING

    await storage.mark_done(key=key, now=shifted_send)
    assert not await storage.plan(
        key=key,
        now=shifted_send,
        send_at=first_send,
        expires_at=first_expiry,
    )
    await session.commit()
    await session.refresh(model)
    assert await session.scalar(select(ReminderDeliveryModel.status)) == DeliveryStatus.DONE
    assert model.scheduled_at == shifted_send


async def test_replanner_does_not_take_over_claimed_delivery(session: AsyncSession) -> None:
    now = datetime(2026, 12, 25, 9, tzinfo=UTC)
    key = ReminderDeliveryKey(
        connection_id="c" * 32,
        kind=ReminderKind.BIRTHDAY,
        item_id="i" * 32,
        occurrence_date=date(2027, 1, 1),
        lead_days=7,
    )
    storage = ReminderDatabaseStorage(session=session)
    assert await storage.plan(
        key=key,
        now=now,
        send_at=now,
        expires_at=now + timedelta(hours=15),
    )
    assert await storage.claim_due(
        now=now,
        lease_until=now + timedelta(minutes=5),
        max_attempts=3,
    )
    assert not await storage.plan(
        key=key,
        now=now,
        send_at=now + timedelta(hours=5),
        expires_at=now + timedelta(hours=20),
    )
    model = await session.scalar(select(ReminderDeliveryModel))
    assert model is not None
    assert model.status == DeliveryStatus.IN_PROGRESS


async def test_auth_outage_defers_claim_without_spending_telegram_attempt(
    session: AsyncSession,
) -> None:
    now = datetime(2026, 12, 25, 9, tzinfo=UTC)
    key = ReminderDeliveryKey(
        connection_id="c" * 32,
        kind=ReminderKind.BIRTHDAY,
        item_id="i" * 32,
        occurrence_date=date(2027, 1, 1),
        lead_days=7,
    )
    storage = ReminderDatabaseStorage(session=session)
    assert await storage.plan(
        key=key,
        now=now,
        send_at=now,
        expires_at=now + timedelta(hours=15),
    )
    claimed = await storage.claim_due(
        now=now,
        lease_until=now + timedelta(minutes=5),
        max_attempts=3,
    )
    assert claimed is not None
    assert claimed.attempts == 1
    await storage.defer_without_attempt(
        key=key,
        now=now,
        next_attempt_at=now + timedelta(minutes=15),
    )
    await session.commit()
    model = await session.scalar(select(ReminderDeliveryModel))
    assert model is not None
    assert model.status == DeliveryStatus.RETRY
    assert model.attempts == 0
    assert model.next_attempt_at == now + timedelta(minutes=15)


async def test_dispatchers_cannot_claim_the_same_pending_delivery(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime(2026, 12, 25, 9, tzinfo=UTC)
    key = ReminderDeliveryKey(
        connection_id="c" * 32,
        kind=ReminderKind.BIRTHDAY,
        item_id="i" * 32,
        occurrence_date=date(2027, 1, 1),
        lead_days=7,
    )
    await ReminderDatabaseStorage(session=session).plan(
        key=key,
        now=now,
        send_at=now,
        expires_at=now + timedelta(hours=15),
    )
    await session.commit()

    async def claim() -> bool:
        async with session_maker() as db:
            result = await ReminderDatabaseStorage(session=db).claim_due(
                now=now,
                lease_until=now + timedelta(minutes=5),
                max_attempts=3,
            )
            await db.commit()
            return result is not None

    assert sorted(await asyncio.gather(claim(), claim())) == [False, True]
    delivery = await session.scalar(select(ReminderDeliveryModel))
    assert delivery is not None
    await session.refresh(delivery)
    assert delivery.attempts == 1


async def test_pending_delivery_waits_until_recipient_local_nine(session: AsyncSession) -> None:
    now = datetime(2026, 12, 25, 8, 30, tzinfo=UTC)
    send_at = datetime(2026, 12, 25, 9, tzinfo=UTC)
    storage = ReminderDatabaseStorage(session=session)
    key = ReminderDeliveryKey(
        connection_id="c" * 32,
        kind=ReminderKind.BIRTHDAY,
        item_id="i" * 32,
        occurrence_date=date(2027, 1, 1),
        lead_days=7,
    )
    assert await storage.plan(
        key=key,
        now=now,
        send_at=send_at,
        expires_at=now + timedelta(hours=15, minutes=30),
    )
    await session.commit()
    assert (
        await storage.claim_due(
            now=send_at - timedelta(seconds=1),
            lease_until=send_at + timedelta(minutes=5),
            max_attempts=3,
        )
        is None
    )
    assert (
        await storage.claim_due(
            now=send_at,
            lease_until=send_at + timedelta(minutes=5),
            max_attempts=3,
        )
        is not None
    )


async def test_cleanup_expires_pending_and_removes_terminal_history_after_90_days(
    session: AsyncSession,
) -> None:
    now = datetime(2027, 4, 1, 9, tzinfo=UTC)
    storage = ReminderDatabaseStorage(session=session)
    expired_key = ReminderDeliveryKey(
        connection_id="c" * 32,
        kind=ReminderKind.BIRTHDAY,
        item_id="i" * 32,
        occurrence_date=date(2027, 1, 1),
        lead_days=7,
    )
    old_done_key = ReminderDeliveryKey(
        connection_id="c" * 32,
        kind=ReminderKind.MEMORABLE_DATE,
        item_id="d" * 32,
        occurrence_date=date(2026, 12, 31),
        lead_days=7,
    )
    old_time = now - timedelta(days=91)
    await storage.plan(
        key=expired_key,
        now=old_time,
        send_at=old_time,
        expires_at=old_time + timedelta(days=1),
    )
    await storage.plan(
        key=old_done_key,
        now=old_time,
        send_at=old_time,
        expires_at=old_time + timedelta(days=1),
    )
    await storage.mark_done(key=old_done_key, now=old_time)
    await session.commit()

    assert await storage.expire_and_prune(now=now, retention=timedelta(days=90)) == 1
    await session.commit()
    remaining = (await session.scalars(select(ReminderDeliveryModel))).all()
    assert len(remaining) == 1
    assert remaining[0].status == DeliveryStatus.EXPIRED


async def test_reminder_sources_are_owner_scoped_and_include_related_people(
    session: AsyncSession,
) -> None:
    items = KnowledgeItemsDatabaseStorage(session=session)
    dates = KnowledgeDatesDatabaseStorage(session=session)
    people = PeopleDatabaseStorage(session=session)
    person = await items.create_item(
        params=KnowledgeItemCreateParams(
            kind=KnowledgeItemKind.PERSON,
            author_username="owner-a",
            display_name="Anna Ivanova",
            description="",
        ),
    )
    await people.create_details(
        details=PersonDetails(
            item_id=person.id,
            last_name="Ivanova",
            first_name="Anna",
            middle_name="",
            email="",
            phone="",
            telegram="",
            birthday=PersonBirthday(day=1, month=1, year=2000),
            notifications_enabled=True,
        ),
        author_username="owner-a",
    )
    for owner, enabled in (("owner-a", True), ("owner-b", True), ("owner-a", False)):
        item = await items.create_item(
            params=KnowledgeItemCreateParams(
                kind=KnowledgeItemKind.DATE,
                author_username=owner,
                display_name=f"Wedding {owner} {enabled}",
                description="Celebrate **together**",
            ),
        )
        await dates.create_details(
            details=KnowledgeDateDetails(
                item_id=item.id,
                date=KnowledgeDateValue(day=1, month=1, year=None),
                notifications_enabled=enabled,
            ),
            author_username=owner,
        )
        if owner == "owner-a" and enabled:
            await dates.replace_person_links(
                date_id=item.id,
                person_ids=[person.id],
                author_username=owner,
            )

    reminders = ReminderDatabaseStorage(session=session)
    birthdays = await reminders.list_sources(
        owner_username="owner-a",
        kind=ReminderKind.BIRTHDAY,
        occurrence_date=date(2027, 1, 1),
    )
    memorable_dates = await reminders.list_sources(
        owner_username="owner-a",
        kind=ReminderKind.MEMORABLE_DATE,
        occurrence_date=date(2027, 1, 1),
    )
    assert [(item.title, item.year) for item in birthdays] == [("Anna Ivanova", 2000)]
    assert len(memorable_dates) == 1
    assert memorable_dates[0].related_people == ("Anna Ivanova",)
    assert memorable_dates[0].description == "Celebrate **together**"

    telegram = TelegramDatabaseStorage(session=session)
    connection = await telegram.create_pending_connection(
        owner_username="owner-a",
        participant=TelegramParticipant(
            user_id=42,
            private_chat_id=42,
            first_name="Anna",
            username="anna",
        ),
        label="Family",
        now=datetime(2026, 12, 25, 9, tzinfo=UTC),
    )
    await telegram.set_connection_state(
        connection_id=connection.id,
        state=TelegramConnectionState.ACTIVE,
        now=datetime(2026, 12, 25, 9, tzinfo=UTC),
    )
    await telegram.set_connection_settings(
        connection_id=connection.id,
        settings=TelegramConnectionSettings(
            notify_birthday=False,
            notify_memorable_date=True,
            language=LanguageEnum.EN,
        ),
    )
    key = ReminderDeliveryKey(
        connection_id=connection.id,
        kind=ReminderKind.MEMORABLE_DATE,
        item_id=memorable_dates[0].item_id,
        occurrence_date=date(2027, 1, 1),
        lead_days=7,
    )
    assert (
        await reminders.get_current(
            key=key,
            now=datetime(2026, 12, 25, 9, tzinfo=UTC),
            local_send_time=time(9),
            time_zone=ZoneInfo("UTC"),
        )
        is not None
    )
    await session.execute(
        update(KnowledgeDateDetailsModel)
        .where(KnowledgeDateDetailsModel.item_id == key.item_id)
        .values(notifications_enabled=False),
    )
    assert (
        await reminders.get_current(
            key=key,
            now=datetime(2026, 12, 25, 9, tzinfo=UTC),
            local_send_time=time(9),
            time_zone=ZoneInfo("UTC"),
        )
        is None
    )
