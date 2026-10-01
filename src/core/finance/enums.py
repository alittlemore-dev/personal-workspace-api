from enum import StrEnum
from typing import TYPE_CHECKING

from core.enums import TranslationStrEnum
from core.finance.exceptions import InvalidFinanceDataError
from core.i18n.enums import LanguageEnum

if TYPE_CHECKING:
    from core.finance.schemas import Amount


class FinanceCurrency(StrEnum):
    AMD = "AMD"
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"

    def validate_money(self, amount: Amount, *, positive: bool) -> None:
        amount.validate_precision(self)
        if amount < 0 or (positive and amount == 0):
            raise InvalidFinanceDataError

    @classmethod
    def for_language(cls, language: LanguageEnum) -> FinanceCurrency:
        return cls.RUB if language == LanguageEnum.RU else cls.USD


class FinanceKind(TranslationStrEnum):
    INCOME = "income", "Доход", "Income"
    EXPENSE = "expense", "Расход", "Expense"


class FinanceSource(StrEnum):
    WEB = "web"
    TELEGRAM = "telegram"


class FinanceEventKind(StrEnum):
    TRANSACTION = "finance.transaction_by_other"
    LIMIT = "finance.expense_limit_exceeded"


class FinanceLimitScope(StrEnum):
    CATEGORY = "category"
    MONTH = "month"


class FinanceRevisionAction(StrEnum):
    UPDATE = "update"
    DELETE = "delete"
    RESTORE = "restore"
