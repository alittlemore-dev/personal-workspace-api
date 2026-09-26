from datetime import datetime

from dishka.integrations.taskiq import FromDishka, inject

from core.notifications.use_cases import (
    PlanRemindersUseCase,
    PruneRemindersUseCase,
    SendRemindersUseCase,
)
from entrypoints.taskiq.broker import broker
from infra.config.constants import constants
from infra.config.settings import settings


@broker.task(
    constants.taskiq.plan_reminders_task_name,
    schedule=[
        {
            "schedule_id": constants.taskiq.plan_reminders_task_name,
            "interval": constants.telegram.reminder_scan_interval_seconds,
        },
    ],
)
@inject(patch_module=True)
async def plan_reminders(
    use_case: FromDishka[PlanRemindersUseCase],
    current_datetime: FromDishka[datetime],
) -> int:
    if not settings.telegram.available:
        return 0
    return await use_case.run(now=current_datetime)


@broker.task(
    constants.taskiq.send_reminders_task_name,
    schedule=[
        {
            "schedule_id": constants.taskiq.send_reminders_task_name,
            "interval": constants.telegram.reminder_scan_interval_seconds,
        },
    ],
)
@inject(patch_module=True)
async def send_reminders(
    use_case: FromDishka[SendRemindersUseCase],
    current_datetime: FromDishka[datetime],
) -> int:
    if not settings.telegram.available:
        return 0
    return await use_case.run(now=current_datetime)


@broker.task(
    constants.taskiq.prune_reminders_task_name,
    schedule=[
        {
            "schedule_id": constants.taskiq.prune_reminders_task_name,
            "interval": constants.telegram.reminder_prune_interval_seconds,
        },
    ],
)
@inject(patch_module=True)
async def prune_reminders(
    use_case: FromDishka[PruneRemindersUseCase],
    current_datetime: FromDishka[datetime],
) -> int:
    return await use_case.run(now=current_datetime)
