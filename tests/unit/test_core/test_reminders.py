from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import AsyncMock

import pytest

from core.i18n.enums import LanguageEnum
from core.notifications.clients import ReminderSender, RetryableReminderSendError
from core.notifications.enums import ReminderKind
from core.notifications.schemas import (
    ReminderDelivery,
    ReminderDeliveryKey,
    ReminderRecipient,
    ReminderSchedule,
    ReminderSource,
    ReminderWindow,
)
from core.notifications.services import ReminderDeliveryService, ReminderTextFormatter
from core.notifications.storages import ReminderStorage
from core.notifications.use_cases import (
    PlanRemindersUseCase,
    PruneRemindersUseCase,
    SendRemindersUseCase,
)
from core.telegram.storages import TelegramAccountSettingsReader, TelegramTransaction

NOW = datetime(2026, 12, 25, 9, tzinfo=UTC)


def recipient(*, notify_birthday: bool = True) -> ReminderRecipient:
    return ReminderRecipient(
        connection_id="c" * 32,
        owner_username="owner",
        private_chat_id=42,
        notify_birthday=notify_birthday,
        notify_memorable_date=False,
        language=LanguageEnum.RU,
        time_zone="UTC",
    )


def source() -> ReminderSource:
    return ReminderSource(
        owner_username="owner",
        item_id="i" * 32,
        kind=ReminderKind.BIRTHDAY,
        title="Анна",
        day=1,
        month=1,
        year=2000,
        description="",
        related_people=(),
        notifications_enabled=True,
    )


SCHEDULE = ReminderSchedule(
    scan_batch_size=100,
    max_attempts=3,
    retry_interval=timedelta(minutes=15),
    claim_lease=timedelta(minutes=5),
    local_send_time=time(9),
)


def setup_planner(
    *,
    target: ReminderSource | None = None,
    target_recipient: ReminderRecipient | None = None,
) -> tuple[PlanRemindersUseCase, AsyncMock, AsyncMock]:
    item = target or source()
    connection = target_recipient or recipient()
    storage = AsyncMock(spec=ReminderStorage)
    storage.list_recipients.return_value = [connection]
    storage.list_sources.side_effect = lambda **kwargs: (
        [item]
        if kwargs["kind"] == item.kind and kwargs["occurrence_date"] == date(2027, 1, 1)
        else []
    )
    storage.plan.return_value = True
    transaction = AsyncMock(spec=TelegramTransaction)
    use_case = PlanRemindersUseCase(
        storage=storage,
        transaction=transaction,
        schedule=SCHEDULE,
    )
    return use_case, storage, transaction


def setup_sender(
    *,
    attempts: int = 1,
    expires_at: datetime = NOW + timedelta(hours=15),
) -> tuple[SendRemindersUseCase, AsyncMock, AsyncMock, AsyncMock, AsyncMock]:
    storage = AsyncMock(spec=ReminderStorage)
    storage.claim_due.side_effect = [
        ReminderDelivery(
            key=ReminderDeliveryKey(
                connection_id="c" * 32,
                kind=ReminderKind.BIRTHDAY,
                item_id="i" * 32,
                occurrence_date=date(2027, 1, 1),
                lead_days=7,
            ),
            attempts=attempts,
            expires_at=expires_at,
        ),
        None,
    ]
    storage.get_current.return_value = (recipient(), source())
    reader = AsyncMock(spec=TelegramAccountSettingsReader)
    reader.can_notify.return_value = True
    sender = AsyncMock(spec=ReminderSender)
    transaction = AsyncMock(spec=TelegramTransaction)
    use_case = SendRemindersUseCase(
        storage=storage,
        delivery_service=ReminderDeliveryService(
            settings_reader=reader,
            sender=sender,
            formatter=ReminderTextFormatter(description_limit=300),
        ),
        transaction=transaction,
        schedule=SCHEDULE,
    )
    return use_case, storage, reader, sender, transaction


@pytest.mark.asyncio
async def test_week_reminder_crosses_new_year_and_uses_recipient_language() -> None:
    planner, planned_storage, _ = setup_planner()
    assert await planner.run(now=NOW) == 1
    assert planned_storage.plan.await_args.kwargs["key"].occurrence_date == date(2027, 1, 1)
    assert planned_storage.plan.await_args.kwargs["key"].lead_days == 7

    use_case, storage, _, sender, transaction = setup_sender()
    assert await use_case.run(now=NOW) == 1
    assert sender.send.await_args.kwargs == {
        "private_chat_id": 42,
        "text": "Через 7 дн. · 01.01.2027\nДень рождения: Анна (исполнится 27)",
    }
    storage.mark_done.assert_awaited_once()
    assert transaction.commit.await_count == 3


@pytest.mark.asyncio
async def test_before_nine_plans_delivery_for_nine() -> None:
    use_case, storage, _ = setup_planner()
    assert await use_case.run(now=NOW - timedelta(minutes=1)) == 1
    assert storage.plan.await_args.kwargs["send_at"] == NOW


@pytest.mark.asyncio
async def test_bot_notification_switch_cancels_pending_delivery() -> None:
    use_case, storage, reader, sender, _ = setup_sender()
    reader.can_notify.return_value = False
    assert await use_case.run(now=NOW) == 0
    storage.mark_canceled.assert_awaited_once()
    sender.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_missed_local_day_is_not_caught_up() -> None:
    planner, storage, _ = setup_planner()
    assert await planner.run(now=NOW + timedelta(days=1)) == 0
    storage.plan.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_card_or_type_does_not_plan_delivery() -> None:
    disabled = replace(source(), notifications_enabled=False)
    use_case, storage, _ = setup_planner(target=disabled)
    assert await use_case.run(now=NOW) == 0
    storage.plan.assert_not_awaited()

    use_case, storage, _ = setup_planner(target_recipient=recipient(notify_birthday=False))
    assert await use_case.run(now=NOW) == 0
    storage.plan.assert_not_awaited()


@pytest.mark.asyncio
async def test_source_changed_after_claim_is_canceled() -> None:
    use_case, storage, _, sender, _ = setup_sender()
    storage.get_current.return_value = None
    assert await use_case.run(now=NOW) == 0
    storage.mark_canceled.assert_awaited_once()
    sender.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_transient_telegram_error_schedules_bounded_retry() -> None:
    use_case, storage, _, sender, _ = setup_sender()
    sender.send.side_effect = RetryableReminderSendError(retry_after_seconds=1800)
    assert await use_case.run(now=NOW) == 0
    assert storage.mark_retry.await_args.kwargs["next_attempt_at"] == NOW + timedelta(minutes=30)


@pytest.mark.asyncio
async def test_retry_stops_at_attempt_limit_or_local_midnight() -> None:
    use_case, storage, _, sender, _ = setup_sender(attempts=3)
    sender.send.side_effect = RetryableReminderSendError(retry_after_seconds=0)
    assert await use_case.run(now=NOW) == 0
    storage.mark_failed.assert_awaited_once()

    use_case, storage, _, sender, _ = setup_sender(expires_at=NOW + timedelta(minutes=10))
    sender.send.side_effect = RetryableReminderSendError(retry_after_seconds=0)
    assert await use_case.run(now=NOW) == 0
    storage.mark_expired.assert_awaited_once()


@pytest.mark.asyncio
async def test_pruner_expires_old_deliveries_and_removes_90_day_history() -> None:
    storage = AsyncMock(spec=ReminderStorage)
    storage.expire_and_prune.return_value = 4
    transaction = AsyncMock(spec=TelegramTransaction)
    pruner = PruneRemindersUseCase(
        storage=storage,
        transaction=transaction,
        retention=timedelta(days=90),
    )
    assert await pruner.run(now=NOW) == 4
    storage.expire_and_prune.assert_awaited_once_with(
        now=NOW,
        retention=timedelta(days=90),
    )
    transaction.commit.assert_awaited_once()


def test_message_includes_people_and_plain_text_excerpt_in_each_language() -> None:
    formatter = ReminderTextFormatter(description_limit=300)
    item = replace(
        source(),
        kind=ReminderKind.MEMORABLE_DATE,
        title="Свадьба",
        description="**Собраться** [в кафе](https://example.com) <b>вместе</b>",
        related_people=("Анна", "Борис"),
    )
    ru = formatter.format(
        source=item,
        occurrence_date=date(2027, 1, 1),
        lead_days=1,
        language=LanguageEnum.RU,
    )
    en = formatter.format(
        source=item,
        occurrence_date=date(2027, 1, 1),
        lead_days=1,
        language=LanguageEnum.EN,
    )
    assert "Связанные люди: Анна, Борис" in ru
    assert "Related people: Анна, Борис" in en
    assert "Собраться в кафе вместе" in ru
    assert "**" not in ru
    assert "<b>" not in ru
    assert "https://" not in ru


def test_description_excerpt_is_limited_to_300_plain_characters() -> None:
    formatter = ReminderTextFormatter(description_limit=300)
    excerpt = formatter.description_excerpt(markdown="**" + "a" * 400 + "**")
    assert excerpt == "a" * 300


def test_leap_day_is_not_an_occurrence_on_february_28() -> None:
    item = replace(source(), day=29, month=2, year=None)
    assert not item.occurs_on(day=date(2027, 2, 28))
    assert item.occurs_on(day=date(2028, 2, 29))


@pytest.mark.parametrize(
    ("instant", "local_day", "send_hour_utc", "eligible"),
    [
        (datetime(2027, 3, 14, 12, 59, tzinfo=UTC), date(2027, 3, 14), 13, False),
        (datetime(2027, 3, 14, 13, tzinfo=UTC), date(2027, 3, 14), 13, True),
        (datetime(2027, 11, 7, 13, 59, tzinfo=UTC), date(2027, 11, 7), 14, False),
        (datetime(2027, 11, 7, 14, tzinfo=UTC), date(2027, 11, 7), 14, True),
        (datetime(2027, 3, 15, 1, tzinfo=UTC), date(2027, 3, 14), 13, True),
    ],
)
def test_local_nine_follows_dst_and_local_day(
    instant: datetime,
    local_day: date,
    send_hour_utc: int,
    eligible: bool,
) -> None:
    window = ReminderWindow.for_connection(
        now=instant,
        time_zone="America/New_York",
        local_send_time=time(9),
    )
    assert window.local_date == local_day
    assert window.send_at == datetime.combine(local_day, time(send_hour_utc), tzinfo=UTC)
    assert window.eligible is eligible
