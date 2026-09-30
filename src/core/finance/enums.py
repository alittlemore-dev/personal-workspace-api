from enum import StrEnum
from typing import TYPE_CHECKING

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


class FinanceKind(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"


class FinanceRevisionAction(StrEnum):
    UPDATE = "update"
    DELETE = "delete"
    RESTORE = "restore"
