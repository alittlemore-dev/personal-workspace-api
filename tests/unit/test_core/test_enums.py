import json

import pytest

from core.finance.enums import FinanceKind
from core.i18n.enums import LanguageEnum


@pytest.mark.parametrize(
    ("kind", "value", "value_ru", "value_en"),
    [
        (FinanceKind.INCOME, "income", "Доход", "Income"),
        (FinanceKind.EXPENSE, "expense", "Расход", "Expense"),
    ],
)
def test_translation_enum_preserves_value_and_selects_language(
    kind: FinanceKind,
    value: str,
    value_ru: str,
    value_en: str,
) -> None:
    assert kind.get_translation(LanguageEnum.RU) == kind.value_ru == value_ru
    assert kind.get_translation(LanguageEnum.EN) == kind.value_en == value_en
    assert str(kind) == kind.value == value
    assert FinanceKind.from_value(json.loads(json.dumps(kind))) is kind
