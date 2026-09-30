from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from typing import cast
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from core.account_time_zone.clients import (
    AccountTimeZoneReader,
    AccountTimeZoneUnavailableError,
)
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
from core.notifications.services import (
    ReminderDeliveryService,
    ReminderProcessingService,
    ReminderTextFormatter,
)
from core.notifications.storages import ReminderStorage
from core.notifications.use_cases import (
    PlanRemindersUseCase,
    PruneRemindersUseCase,
    SendRemindersUseCase,
)
from core.telegram.storages import TelegramAccountSettingsReader, TelegramTransaction
from tests.helpers.factories.core import CoreFactoryHelper

NOW = datetime(2026, 12, 25, 9, tzinfo=UTC)


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
    item = target or CoreFactoryHelper.reminder_source()
    connection = target_recipient or CoreFactoryHelper.reminder_recipient()
    storage = AsyncMock(spec=ReminderStorage)
    storage.list_recipients.return_value = [connection]
    storage.list_sources.side_effect = lambda **kwargs: (
        [item]
        if kwargs["kind"] == item.kind and kwargs["occurrence_date"] == date(2027, 1, 1)
        else []
    )
    storage.plan.return_value = True
    transaction = AsyncMock(spec=TelegramTransaction)
    account_time_zone_reader = AsyncMock(spec=AccountTimeZoneReader)
    account_time_zone_reader.get_time_zone.return_value = ZoneInfo("UTC")
    use_case = PlanRemindersUseCase(
        storage=storage,
        transaction=transaction,
        schedule=SCHEDULE,
        account_time_zone_reader=account_time_zone_reader,
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
            scheduled_at=NOW,
            expires_at=expires_at,
        ),
        None,
    ]
    storage.get_current.return_value = (
        CoreFactoryHelper.reminder_recipient(),
        CoreFactoryHelper.reminder_source(),
    )
    storage.get_recipient.return_value = CoreFactoryHelper.reminder_recipient()
    reader = AsyncMock(spec=TelegramAccountSettingsReader)
    reader.can_notify.return_value = True
    account_time_zone_reader = AsyncMock(spec=AccountTimeZoneReader)
    account_time_zone_reader.get_time_zone.return_value = ZoneInfo("UTC")
    sender = AsyncMock(spec=ReminderSender)
    transaction = AsyncMock(spec=TelegramTransaction)
    use_case = SendRemindersUseCase(
        storage=storage,
        processing_service=ReminderProcessingService(
            storage=storage,
            delivery_service=ReminderDeliveryService(
                settings_reader=reader,
                sender=sender,
                formatter=ReminderTextFormatter(description_limit=300),
            ),
            schedule=SCHEDULE,
            account_time_zone_reader=account_time_zone_reader,
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
async def test_one_account_zone_plans_all_recipients_at_same_local_nine() -> None:
    use_case, storage, _ = setup_planner()
    storage.list_recipients.return_value = [
        CoreFactoryHelper.reminder_recipient(),
        replace(CoreFactoryHelper.reminder_recipient(), connection_id="d" * 32),
    ]
    reader = cast("AsyncMock", use_case.account_time_zone_reader)
    reader.get_time_zone.return_value = ZoneInfo("America/New_York")

    assert await use_case.run(now=NOW) == 2
    assert storage.plan.await_count == 2
    assert all(
        call.kwargs["send_at"] == datetime(2026, 12, 25, 14, tzinfo=UTC)
        for call in storage.plan.await_args_list
    )


@pytest.mark.asyncio
async def test_account_zone_unavailable_skips_planning_without_utc_fallback() -> None:
    use_case, storage, _ = setup_planner()
    reader = cast("AsyncMock", use_case.account_time_zone_reader)
    reader.get_time_zone.side_effect = AccountTimeZoneUnavailableError()

    assert await use_case.run(now=NOW) == 0
    storage.plan.assert_not_awaited()


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
    disabled = replace(CoreFactoryHelper.reminder_source(), notifications_enabled=False)
    use_case, storage, _ = setup_planner(target=disabled)
    assert await use_case.run(now=NOW) == 0
    storage.plan.assert_not_awaited()

    use_case, storage, _ = setup_planner(
        target_recipient=CoreFactoryHelper.reminder_recipient(notify_birthday=False),
    )
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
async def test_stale_queued_delivery_moves_to_new_account_local_nine() -> None:
    use_case, storage, _, sender, _ = setup_sender()
    reader = cast("AsyncMock", use_case.processing_service.account_time_zone_reader)
    reader.get_time_zone.return_value = ZoneInfo("America/New_York")

    assert await use_case.run(now=NOW) == 0
    storage.reschedule.assert_awaited_once_with(
        key=ReminderDeliveryKey(
            connection_id="c" * 32,
            kind=ReminderKind.BIRTHDAY,
            item_id="i" * 32,
            occurrence_date=date(2027, 1, 1),
            lead_days=7,
        ),
        now=NOW,
        send_at=datetime(2026, 12, 25, 14, tzinfo=UTC),
        expires_at=datetime(2026, 12, 26, 5, tzinfo=UTC),
    )
    storage.mark_canceled.assert_not_awaited()
    sender.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_zone_change_to_previous_local_day_cancels_old_occurrence_key() -> None:
    use_case, storage, _, sender, _ = setup_sender()
    reader = cast("AsyncMock", use_case.processing_service.account_time_zone_reader)
    reader.get_time_zone.return_value = ZoneInfo("Pacific/Honolulu")

    assert await use_case.run(now=NOW) == 0
    storage.mark_canceled.assert_awaited_once()
    storage.reschedule.assert_not_awaited()
    sender.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_account_zone_read_failure_never_sends_queued_delivery() -> None:
    use_case, storage, _, sender, _ = setup_sender(attempts=3)
    reader = cast("AsyncMock", use_case.processing_service.account_time_zone_reader)
    reader.get_time_zone.side_effect = AccountTimeZoneUnavailableError()

    assert await use_case.run(now=NOW) == 0
    storage.defer_without_attempt.assert_awaited_once_with(
        key=ReminderDeliveryKey(
            connection_id="c" * 32,
            kind=ReminderKind.BIRTHDAY,
            item_id="i" * 32,
            occurrence_date=date(2027, 1, 1),
            lead_days=7,
        ),
        now=NOW,
        next_attempt_at=NOW + timedelta(minutes=15),
    )
    storage.mark_failed.assert_not_awaited()
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

    use_case, storage, _, sender, _ = setup_sender()
    sender.send.side_effect = RetryableReminderSendError(retry_after_seconds=0)
    assert await use_case.run(now=NOW + timedelta(hours=14, minutes=50)) == 0
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
        CoreFactoryHelper.reminder_source(),
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
    item = replace(CoreFactoryHelper.reminder_source(), day=29, month=2, year=None)
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
    window = ReminderWindow.for_account(
        now=instant,
        time_zone=ZoneInfo("America/New_York"),
        local_send_time=time(9),
    )
    assert window.local_date == local_day
    assert window.send_at == datetime.combine(local_day, time(send_hour_utc), tzinfo=UTC)
    assert window.eligible is eligible
