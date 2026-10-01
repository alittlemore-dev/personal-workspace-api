from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from core.finance.enums import FinanceEventKind, FinanceKind, FinanceLimitScope, FinanceSource
from core.finance.event_dispatchers import FinanceEventDispatcher
from core.finance.schemas import (
    Amount,
    FinanceEvent,
    FinanceEventConfig,
    FinanceEventPayload,
    TelegramFinanceContextParams,
)
from core.finance.services import FinanceEventService, FinanceTelegramAccessService
from core.finance.storages import FinanceStorage
from core.i18n.enums import LanguageEnum
from core.notifications.clients import (
    PermanentReminderSendError,
    ReminderSender,
    RetryableReminderSendError,
)
from core.notifications.enums import DeliveryStatus
from core.notifications.finance import (
    FinanceDelivery,
    FinanceDeliveryConfig,
    FinanceDeliveryStorage,
    FinanceNotificationFormatter,
    ProcessFinanceNotificationsUseCase,
)
from core.telegram.exceptions import TelegramAccessError
from core.telegram.storages import (
    TelegramAccountSettingsReader,
    TelegramStorage,
    TelegramTransaction,
)
from tests.test_cases import TestCase

NOW = datetime(2026, 9, 15, 12, tzinfo=UTC)


class TestFinanceNotifications(TestCase):
    @pytest.mark.parametrize(
        ("before_amount", "after_amount", "plan", "expected"),
        [
            ("9", "10", "10", 0),
            ("10", "11", "10", 2),
            ("11", "12", "10", 0),
            ("0", "1", "0", 2),
            ("0", "1", None, 0),
            ("12", "9", "10", 0),
        ],
    )
    def test_limit_crossings_match_category_and_month_plans(
        self,
        before_amount: str,
        after_amount: str,
        plan: str | None,
        expected: int,
    ) -> None:
        category = self.factory.core.finance_category(
            planned_amount=plan,
            actual_amount=before_amount,
        )
        before = self.factory.core.finance_month(
            actual_expense=before_amount,
            planned_expense=plan,
            categories=[category],
        )
        after = replace(
            before,
            actual_expense=Amount(after_amount),
            categories=[replace(category, actual_amount=Amount(after_amount))],
        )
        events = after.crossed_limits(before, self.factory.core.finance_transaction())
        assert len(events) == expected
        if events:
            assert {e.limit_scope for e in events} == {
                FinanceLimitScope.CATEGORY,
                FinanceLimitScope.MONTH,
            }

    async def test_creation_emits_event_and_atomic_limit_transitions(self) -> None:
        category = self.factory.core.finance_category(planned_amount="10", actual_amount="10")
        before = self.factory.core.finance_month(
            actual_expense="10",
            planned_expense="10",
            categories=[category],
        )
        after = replace(
            before,
            actual_expense=Amount(11),
            categories=[replace(category, actual_amount=Amount(11))],
        )
        dispatcher = AsyncMock(spec=FinanceEventDispatcher)
        service = FinanceEventService(
            dispatcher=dispatcher,
            config=FinanceEventConfig(lifetime=timedelta(days=1)),
        )
        await service.created(
            owner_username="owner",
            before=before,
            after=after,
            transaction=self.factory.core.finance_transaction(),
            now=NOW,
        )
        assert [c.kwargs["event"].kind for c in dispatcher.publish.call_args_list] == [
            FinanceEventKind.TRANSACTION,
            FinanceEventKind.LIMIT,
            FinanceEventKind.LIMIT,
        ]
        assert all(
            c.kwargs["event"].expires_at == NOW + timedelta(days=1)
            for c in dispatcher.publish.call_args_list
        )

    def delivery(self) -> FinanceDelivery:
        transaction = self.factory.core.finance_transaction()
        month = self.factory.core.finance_month()
        return FinanceDelivery(
            id="delivery",
            attempts=1,
            connection=self.factory.core.telegram_connection(),
            event=FinanceEvent(
                owner_username="owner",
                kind=FinanceEventKind.TRANSACTION,
                payload=FinanceEventPayload.for_transaction(month, transaction),
                created_at=NOW,
                expires_at=NOW + timedelta(days=1),
            ),
        )

    def test_web_creation_notifies_all_and_telegram_excludes_only_author(self) -> None:
        delivery = self.delivery()
        month = self.factory.core.finance_month()
        assert delivery.eligible(month)
        own = replace(
            delivery,
            event=replace(
                delivery.event,
                payload=replace(
                    delivery.event.payload,
                    source=FinanceSource.TELEGRAM.value,
                    author_id="42",
                ),
            ),
        )
        assert not own.eligible(month)
        other = replace(own, connection=self.factory.core.telegram_connection(telegram_user_id=43))
        assert other.eligible(month)
        assert not replace(delivery, connection=None).eligible(month)
        assert not replace(
            delivery,
            connection=self.factory.core.telegram_connection(notify_finance_transaction=False),
        ).eligible(month)

    @pytest.mark.parametrize(
        ("mode", "status"),
        [
            ("success", DeliveryStatus.DONE),
            ("disabled", DeliveryStatus.CANCELED),
            ("changed", DeliveryStatus.CANCELED),
            ("deleted", DeliveryStatus.CANCELED),
            ("expired", DeliveryStatus.EXPIRED),
            ("permanent", DeliveryStatus.FAILED),
            ("temporary", DeliveryStatus.RETRY),
            ("exhausted", DeliveryStatus.FAILED),
            ("revoked", DeliveryStatus.CANCELED),
        ],
    )
    async def test_delivery_rechecks_source_settings_and_records_outcome(
        self,
        mode: str,
        status: DeliveryStatus,
    ) -> None:
        delivery = self.delivery()
        if mode == "expired":
            delivery = replace(delivery, event=replace(delivery.event, expires_at=NOW))
        if mode == "revoked":
            delivery = replace(delivery, connection=None)
        if mode == "exhausted":
            delivery = replace(delivery, attempts=3)
        storage = AsyncMock(spec=FinanceDeliveryStorage)
        storage.claim.side_effect = [delivery, None]
        storage.refresh.return_value = delivery
        finance = AsyncMock(spec=FinanceStorage)
        finance.get_month.return_value = self.factory.core.finance_month()
        finance.get_transaction.return_value = self.factory.core.finance_transaction(
            version=2 if mode == "changed" else 1,
            deleted=mode == "deleted",
        )
        reader = AsyncMock(spec=TelegramAccountSettingsReader)
        reader.can_notify.return_value = mode != "disabled"
        sender = AsyncMock(spec=ReminderSender)
        if mode == "permanent":
            sender.send.side_effect = PermanentReminderSendError
        if mode in ("temporary", "exhausted"):
            sender.send.side_effect = RetryableReminderSendError(retry_after_seconds=1800)
        transaction = AsyncMock(spec=TelegramTransaction)
        use_case = ProcessFinanceNotificationsUseCase(
            storage=storage,
            finance_storage=finance,
            settings_reader=reader,
            sender=sender,
            formatter=FinanceNotificationFormatter(),
            transaction=transaction,
            config=FinanceDeliveryConfig(
                batch_size=2,
                max_attempts=3,
                retry_interval=timedelta(minutes=15),
                claim_lease=timedelta(minutes=5),
                retention=timedelta(days=90),
            ),
        )
        with patch("core.notifications.finance.use_cases.monotonic", return_value=0):
            count = await use_case.run(now=NOW)
        assert count == (1 if mode == "success" else 0)
        assert storage.finish.call_args.kwargs["status"] == status
        if mode == "temporary":
            assert storage.finish.call_args.kwargs["next_attempt_at"] == NOW + timedelta(minutes=30)
        if mode in ("changed", "disabled", "deleted", "expired", "revoked"):
            sender.send.assert_not_awaited()

    @pytest.mark.parametrize("mode", ["source", "expiry"])
    async def test_delivery_revalidates_after_external_settings_check(self, mode: str) -> None:
        delivery = self.delivery()
        if mode == "expiry":
            delivery = replace(
                delivery,
                event=replace(delivery.event, expires_at=NOW + timedelta(seconds=30)),
            )
        elapsed = [0.0]
        storage = AsyncMock(spec=FinanceDeliveryStorage)
        storage.claim.side_effect = [delivery, None]
        storage.refresh.return_value = delivery
        finance = AsyncMock(spec=FinanceStorage)
        finance.get_month.return_value = self.factory.core.finance_month()
        finance.get_transaction.return_value = self.factory.core.finance_transaction()
        reader = AsyncMock(spec=TelegramAccountSettingsReader)

        async def check_settings(*, owner_username: str) -> bool:
            assert owner_username == "owner"
            if mode == "source":
                finance.get_transaction.return_value = self.factory.core.finance_transaction(
                    version=2,
                )
            else:
                elapsed[0] = 60
            return True

        reader.can_notify.side_effect = check_settings
        sender = AsyncMock(spec=ReminderSender)
        use_case = ProcessFinanceNotificationsUseCase(
            storage=storage,
            finance_storage=finance,
            settings_reader=reader,
            sender=sender,
            formatter=FinanceNotificationFormatter(),
            transaction=AsyncMock(spec=TelegramTransaction),
            config=FinanceDeliveryConfig(
                batch_size=2,
                max_attempts=3,
                retry_interval=timedelta(minutes=15),
                claim_lease=timedelta(minutes=5),
                retention=timedelta(days=90),
            ),
        )
        with patch(
            "core.notifications.finance.use_cases.monotonic",
            side_effect=lambda: elapsed[0],
        ):
            assert await use_case.run(now=NOW) == 0
        sender.send.assert_not_awaited()
        assert storage.finish.call_args.kwargs["status"] == (
            DeliveryStatus.CANCELED if mode == "source" else DeliveryStatus.EXPIRED
        )

    @pytest.mark.parametrize(
        ("language", "kind", "direction", "limit_title"),
        [
            (LanguageEnum.RU, FinanceKind.EXPENSE, "Расход", "Превышен лимит"),
            (LanguageEnum.EN, FinanceKind.EXPENSE, "Expense", "Expense limit exceeded"),
            (LanguageEnum.RU, FinanceKind.INCOME, "Доход", "Превышен лимит"),
            (LanguageEnum.EN, FinanceKind.INCOME, "Income", "Expense limit exceeded"),
        ],
    )
    def test_financial_messages_use_connection_language(
        self,
        language: LanguageEnum,
        kind: FinanceKind,
        direction: str,
        limit_title: str,
    ) -> None:
        delivery = self.delivery()
        assert delivery.connection is not None
        delivery = replace(delivery, connection=replace(delivery.connection, language=language))
        delivery = replace(
            delivery,
            event=replace(delivery.event, payload=replace(delivery.event.payload, kind=kind)),
        )
        formatter = FinanceNotificationFormatter()
        text = formatter.format(delivery)
        assert direction in text
        assert delivery.event.payload.author_label in text
        assert delivery.event.payload.category_name in text
        before = self.factory.core.finance_month(planned_expense="5", actual_expense="5")
        after = replace(before, actual_expense=Amount(10))
        payload = after.crossed_limits(before, self.factory.core.finance_transaction())[0]
        limit = replace(
            delivery,
            event=replace(delivery.event, kind=FinanceEventKind.LIMIT, payload=payload),
        )
        text = formatter.format(limit)
        assert limit_title in text
        assert "5 USD" in text
        assert "10 USD" in text
        monthly_limit = replace(
            limit,
            event=replace(
                limit.event,
                payload=replace(payload, limit_scope=FinanceLimitScope.MONTH),
            ),
        )
        monthly_text = formatter.format(monthly_limit)
        assert limit_title in monthly_text
        assert f"{payload.period_start:%m.%Y}" in monthly_text

    async def test_access_fails_closed_without_active_connection_or_enabled_owner(self) -> None:
        storage = AsyncMock(spec=TelegramStorage)
        reader = AsyncMock(spec=TelegramAccountSettingsReader)
        service = FinanceTelegramAccessService(storage=storage, settings_reader=reader)
        params = TelegramFinanceContextParams(telegram_user_id=42, private_chat_id=42, now=NOW)
        storage.active_connection_for_participant.return_value = None
        with pytest.raises(TelegramAccessError):
            await service.resolve(params, lock=False)
        storage.active_connection_for_participant.return_value = (
            self.factory.core.telegram_connection()
        )
        reader.is_enabled.return_value = False
        with pytest.raises(TelegramAccessError):
            await service.resolve(params, lock=False)
