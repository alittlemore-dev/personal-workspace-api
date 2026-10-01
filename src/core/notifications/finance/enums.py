from core.enums import TranslationStrEnum


class FinanceNotificationText(TranslationStrEnum):
    MONTH = "month", "Месяц {period:%m.%Y}", "Month {period:%m.%Y}"
    LIMIT = (
        "limit",
        (
            "Превышен лимит: {title}\nПлан: {plan} {currency}\n"
            "Расходы: {actual} {currency}\nПревышение: {overrun} {currency}"
        ),
        (
            "Expense limit exceeded: {title}\nPlan: {plan} {currency}\n"
            "Expenses: {actual} {currency}\nOverrun: {overrun} {currency}"
        ),
    )
