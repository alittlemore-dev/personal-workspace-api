from collections.abc import AsyncIterator
from datetime import timedelta

import httpx
from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from core.finance.clients import FinanceRateClient
from core.finance.event_dispatchers import FinanceEventDispatcher
from core.finance.schemas import FinanceEventConfig
from core.finance.services import (
    FinanceEventService,
    FinanceMonthService,
    FinanceTelegramAccessService,
)
from core.finance.storages import FinanceStorage
from core.finance.use_cases import FinanceUseCase
from core.notifications.clients import ReminderSender
from core.notifications.finance import (
    FinanceDeliveryConfig,
    FinanceDeliveryStorage,
    FinanceNotificationFormatter,
    ProcessFinanceNotificationsUseCase,
)
from core.telegram.storages import (
    TelegramAccountSettingsReader,
    TelegramStorage,
    TelegramTransaction,
)
from infra.config.constants import constants
from infra.http.finance_rates import BankOfRussiaFinanceRateClient
from infra.postgresql.storages.finance import FinanceDatabaseStorage
from infra.postgresql.storages.finance_notifications import (
    FinanceDatabaseDeliveryStorage,
    FinanceDatabaseEventDispatcher,
)


class FinanceProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_rate_client(self) -> AsyncIterator[FinanceRateClient]:
        async with httpx.AsyncClient(timeout=constants.finance.http_timeout_seconds) as client:
            yield BankOfRussiaFinanceRateClient(http_client=client)

    @provide(scope=Scope.REQUEST)
    def provide_storage(self, session: AsyncSession) -> FinanceStorage:
        return FinanceDatabaseStorage(session=session)

    @provide(scope=Scope.REQUEST)
    def provide_use_case(
        self,
        storage: FinanceStorage,
        rate_client: FinanceRateClient,
        telegram_access: FinanceTelegramAccessService,
        events: FinanceEventService,
        months: FinanceMonthService,
    ) -> FinanceUseCase:
        return FinanceUseCase(
            storage=storage,
            rate_client=rate_client,
            telegram_access=telegram_access,
            events=events,
            months=months,
        )

    @provide(scope=Scope.REQUEST)
    def provide_months(self, storage: FinanceStorage) -> FinanceMonthService:
        return FinanceMonthService(storage=storage)

    @provide(scope=Scope.REQUEST)
    def provide_telegram_access(
        self,
        storage: TelegramStorage,
        settings_reader: TelegramAccountSettingsReader,
    ) -> FinanceTelegramAccessService:
        return FinanceTelegramAccessService(storage=storage, settings_reader=settings_reader)

    @provide(scope=Scope.REQUEST)
    def provide_event_dispatcher(self, session: AsyncSession) -> FinanceEventDispatcher:
        return FinanceDatabaseEventDispatcher(session=session)

    @provide(scope=Scope.REQUEST)
    def provide_events(self, dispatcher: FinanceEventDispatcher) -> FinanceEventService:
        return FinanceEventService(
            dispatcher=dispatcher,
            config=FinanceEventConfig(
                lifetime=timedelta(seconds=constants.finance.event_lifetime_seconds),
            ),
        )

    @provide(scope=Scope.REQUEST)
    def provide_delivery_storage(self, session: AsyncSession) -> FinanceDeliveryStorage:
        return FinanceDatabaseDeliveryStorage(session=session)

    @provide(scope=Scope.REQUEST)
    def provide_notifications(
        self,
        storage: FinanceDeliveryStorage,
        finance_storage: FinanceStorage,
        settings_reader: TelegramAccountSettingsReader,
        sender: ReminderSender,
        transaction: TelegramTransaction,
    ) -> ProcessFinanceNotificationsUseCase:
        return ProcessFinanceNotificationsUseCase(
            storage=storage,
            finance_storage=finance_storage,
            settings_reader=settings_reader,
            sender=sender,
            formatter=FinanceNotificationFormatter(),
            transaction=transaction,
            config=FinanceDeliveryConfig(
                batch_size=constants.telegram.reminder_scan_batch_size,
                max_attempts=constants.telegram.reminder_max_attempts,
                retry_interval=timedelta(
                    seconds=constants.telegram.reminder_retry_interval_seconds,
                ),
                claim_lease=timedelta(seconds=constants.telegram.reminder_claim_lease_seconds),
                retention=timedelta(days=constants.telegram.reminder_retention_days),
            ),
        )
