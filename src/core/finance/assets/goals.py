from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from core.finance.exceptions import InvalidFinanceDataError

MAX_PERCENT = 100


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetGoal:
    month: date
    percent: Decimal
    all_income: bool
    category_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            self.month.day != 1
            or not self.percent.is_finite()
            or not 0 <= self.percent <= MAX_PERCENT
            or self.percent != self.percent.quantize(Decimal("0.01"))
            or self.all_income == bool(self.category_ids)
            or len(set(self.category_ids)) != len(self.category_ids)
        ):
            raise InvalidFinanceDataError

    def includes(self, category_id: str | None) -> bool:
        return self.all_income or category_id in self.category_ids


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetGoalParams:
    owner_username: str
    month: date


@dataclass(frozen=True, slots=True, kw_only=True)
class SetAssetGoalParams:
    owner_username: str
    goal: AssetGoal
