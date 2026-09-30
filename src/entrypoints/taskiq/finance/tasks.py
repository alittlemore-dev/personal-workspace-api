from datetime import datetime

from dishka.integrations.taskiq import FromDishka, inject

from core.finance.use_cases import FinanceUseCase
from entrypoints.taskiq.broker import broker
from infra.config.constants import constants


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
