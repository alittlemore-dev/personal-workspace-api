from dataclasses import dataclass
from datetime import timedelta

from core.finance.enums import FinanceEventKind, FinanceLimitScope, FinanceSource
from core.finance.schemas import FinanceEvent, FinanceMonth
from core.telegram.schemas import TelegramConnection


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceDelivery:
    id: str
    event: FinanceEvent
    connection: TelegramConnection | None
    attempts: int

    def eligible(self, month: FinanceMonth) -> bool:
        connection = self.connection
        if connection is None or connection.owner_username != self.event.owner_username:
            return False
        payload = self.event.payload
        if self.event.kind == FinanceEventKind.TRANSACTION:
            return connection.notify_finance_transaction and not (
                payload.source == FinanceSource.TELEGRAM
                and payload.author_id == str(connection.telegram_user_id)
            )
        if not connection.notify_finance_limit or month.id != payload.month_id:
            return False
        if payload.limit_scope == FinanceLimitScope.MONTH:
            return (
                month.planned_expense is not None and month.actual_expense > month.planned_expense
            )
        category = month.get_category(payload.category_id or "")
        return (
            category.planned_amount is not None and category.actual_amount > category.planned_amount
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceDeliveryConfig:
    batch_size: int
    max_attempts: int
    retry_interval: timedelta
    claim_lease: timedelta
    retention: timedelta
