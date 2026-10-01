from dataclasses import dataclass

from core.finance.enums import FinanceEventKind, FinanceLimitScope
from core.finance.exceptions import FinanceNotFoundError
from core.finance.schemas import Amount
from core.notifications.finance.enums import FinanceNotificationText
from core.notifications.finance.schemas import FinanceDelivery


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceNotificationFormatter:
    def format(self, delivery: FinanceDelivery) -> str:
        if delivery.connection is None:
            raise FinanceNotFoundError
        p = delivery.event.payload
        language = delivery.connection.language
        if delivery.event.kind == FinanceEventKind.TRANSACTION:
            direction = p.kind.get_translation(language)
            amount = p.amount.rounded(p.currency)
            return f"{p.author_label}\n{direction}: {amount} {p.currency}\n{p.category_name}"
        title = (
            p.category_name
            if p.limit_scope == FinanceLimitScope.CATEGORY
            else FinanceNotificationText.MONTH.get_translation(language).format(
                period=p.period_start,
            )
        )
        if p.planned_amount is None or p.actual_amount is None:
            raise FinanceNotFoundError
        over = Amount(p.actual_amount - p.planned_amount).rounded(p.currency)
        return FinanceNotificationText.LIMIT.get_translation(language).format(
            title=title,
            plan=p.planned_amount,
            actual=p.actual_amount,
            overrun=over,
            currency=p.currency,
        )
