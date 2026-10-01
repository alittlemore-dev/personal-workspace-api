from datetime import datetime

from dishka.integrations.taskiq import FromDishka, inject

from core.finance.use_cases import FinanceUseCase
from core.notifications.finance import ProcessFinanceNotificationsUseCase
from entrypoints.taskiq.broker import broker
from infra.config.constants import constants
from infra.config.settings import settings
from infra.valkey.telegram_runtime import TelegramRuntimeStatusStore


@broker.task(
    constants.taskiq.sync_finance_rates_task_name,
    schedule=[
        {
            "schedule_id": constants.taskiq.sync_finance_rates_task_name,
            "interval": constants.finance.sync_interval_seconds,
        },
    ],
)
@inject(patch_module=True)
async def sync_finance_rates(
    use_case: FromDishka[FinanceUseCase],
    current_datetime: FromDishka[datetime],
) -> None:
    await use_case.refresh_rates(on_date=current_datetime.date())


@broker.task(
    constants.taskiq.send_finance_notifications_task_name,
    schedule=[
        {
            "schedule_id": constants.taskiq.send_finance_notifications_task_name,
            "interval": constants.telegram.reminder_scan_interval_seconds,
        },
    ],
)
@inject(patch_module=True)
async def send_finance_notifications(
    use_case: FromDishka[ProcessFinanceNotificationsUseCase],
    current_datetime: FromDishka[datetime],
    runtime_status: FromDishka[TelegramRuntimeStatusStore],
) -> int:
    if not settings.telegram.available or not await runtime_status.is_ready():
        return 0
    return await use_case.run(now=current_datetime)


@broker.task(
    constants.taskiq.prune_finance_notifications_task_name,
    schedule=[
        {
            "schedule_id": constants.taskiq.prune_finance_notifications_task_name,
            "interval": constants.telegram.reminder_prune_interval_seconds,
        },
    ],
)
@inject(patch_module=True)
async def prune_finance_notifications(
    use_case: FromDishka[ProcessFinanceNotificationsUseCase],
    current_datetime: FromDishka[datetime],
) -> int:
    return await use_case.prune(now=current_datetime)
