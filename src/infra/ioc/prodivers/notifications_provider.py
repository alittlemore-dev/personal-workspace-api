from collections.abc import AsyncIterator
from datetime import time, timedelta

from aiogram import Bot
from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from core.notifications.clients import ReminderSender
from core.notifications.schemas import ReminderSchedule
from core.notifications.services import ReminderDeliveryService, ReminderTextFormatter
from core.notifications.storages import ReminderStorage
from core.notifications.use_cases import (
    PlanRemindersUseCase,
    PruneRemindersUseCase,
    SendRemindersUseCase,
)
from core.telegram.storages import TelegramAccountSettingsReader, TelegramTransaction
from infra.config.constants import constants
from infra.config.settings import settings
from infra.postgresql.storages.notifications import ReminderDatabaseStorage
from infra.telegram.reminder_sender import AiogramReminderSender, UnavailableReminderSender


class NotificationsProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_schedule(self) -> ReminderSchedule:
        return ReminderSchedule(
            scan_batch_size=constants.telegram.reminder_scan_batch_size,
            max_attempts=constants.telegram.reminder_max_attempts,
            retry_interval=timedelta(seconds=constants.telegram.reminder_retry_interval_seconds),
            claim_lease=timedelta(seconds=constants.telegram.reminder_claim_lease_seconds),
            local_send_time=time(hour=9),
        )

    @provide(scope=Scope.APP)
    def provide_formatter(self) -> ReminderTextFormatter:
        return ReminderTextFormatter(description_limit=300)

    @provide(scope=Scope.REQUEST)
    def provide_delivery_service(
        self,
        settings_reader: TelegramAccountSettingsReader,
        sender: ReminderSender,
        formatter: ReminderTextFormatter,
    ) -> ReminderDeliveryService:
        return ReminderDeliveryService(
            settings_reader=settings_reader,
            sender=sender,
            formatter=formatter,
        )

    @provide(scope=Scope.APP)
    async def provide_sender(self) -> AsyncIterator[ReminderSender]:
        if not settings.telegram.available:
            yield UnavailableReminderSender()
            return
        bot = Bot(settings.telegram.bot_token.get_secret_value())
        try:
            yield AiogramReminderSender(bot=bot)
        finally:
            await bot.session.close()

    @provide(scope=Scope.REQUEST)
    def provide_storage(self, session: AsyncSession) -> ReminderStorage:
        return ReminderDatabaseStorage(session=session)

    @provide(scope=Scope.REQUEST)
    def provide_planner(
        self,
        storage: ReminderStorage,
        transaction: TelegramTransaction,
        schedule: ReminderSchedule,
    ) -> PlanRemindersUseCase:
        return PlanRemindersUseCase(storage=storage, transaction=transaction, schedule=schedule)

    @provide(scope=Scope.REQUEST)
    def provide_sender_use_case(
        self,
        storage: ReminderStorage,
        delivery_service: ReminderDeliveryService,
        transaction: TelegramTransaction,
        schedule: ReminderSchedule,
    ) -> SendRemindersUseCase:
        return SendRemindersUseCase(
            storage=storage,
            delivery_service=delivery_service,
            transaction=transaction,
            schedule=schedule,
        )

    @provide(scope=Scope.REQUEST)
    def provide_pruner(
        self,
        storage: ReminderStorage,
        transaction: TelegramTransaction,
    ) -> PruneRemindersUseCase:
        return PruneRemindersUseCase(
            storage=storage,
            transaction=transaction,
            retention=timedelta(days=constants.telegram.reminder_retention_days),
        )
