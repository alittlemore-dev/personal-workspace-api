from abc import ABC, abstractmethod
from datetime import date, datetime
from zoneinfo import ZoneInfo

from core.finance.enums import FinanceCurrency
from core.finance.schemas import (
    FinanceCategoryArchival,
    FinanceCategoryCreation,
    FinanceCategoryDeletion,
    FinanceCategoryUpdate,
    FinanceCurrencyChange,
    FinanceMonth,
    FinanceMonthRollover,
    FinanceOpeningBalanceUpdate,
    FinanceRateSet,
    FinanceTemplateCategory,
    FinanceTracker,
    FinanceTransaction,
    FinanceTransactionCreation,
    FinanceTransactionDeletionChange,
    FinanceTransactionRevision,
    FinanceTransactionUpdate,
)
from core.i18n.enums import LanguageEnum


class FinanceStorage(ABC):
    @abstractmethod
    async def lock_tracker(self, *, owner_username: str) -> FinanceTracker | None: ...

    @abstractmethod
    async def create_tracker(
        self,
        *,
        owner_username: str,
        time_zone: ZoneInfo,
        now: datetime,
    ) -> FinanceTracker: ...

    @abstractmethod
    async def latest_month(self, *, tracker: FinanceTracker) -> FinanceMonth | None: ...

    @abstractmethod
    async def archived_category_ids(self, *, tracker: FinanceTracker) -> set[str]: ...

    @abstractmethod
    async def templates(self, *, language: LanguageEnum) -> list[FinanceTemplateCategory]: ...

    @abstractmethod
    async def create_initial_month(
        self,
        *,
        tracker: FinanceTracker,
        period_start: date,
        currency: FinanceCurrency,
        templates: list[FinanceTemplateCategory],
        now: datetime,
    ) -> FinanceMonth: ...

    @abstractmethod
    async def create_rollover_month(
        self,
        *,
        tracker: FinanceTracker,
        rollover: FinanceMonthRollover,
        now: datetime,
    ) -> FinanceMonth: ...

    @abstractmethod
    async def get_month(self, *, owner_username: str, now: datetime) -> FinanceMonth: ...

    @abstractmethod
    async def lock_month(self, *, owner_username: str, now: datetime) -> FinanceMonth: ...

    @abstractmethod
    async def update_opening_balance(
        self,
        *,
        write: FinanceOpeningBalanceUpdate,
    ) -> FinanceMonth: ...

    @abstractmethod
    async def apply_currency_change(self, *, change: FinanceCurrencyChange) -> FinanceMonth: ...

    @abstractmethod
    async def get_rate_set(self, *, rate_set_id: str) -> FinanceRateSet: ...

    @abstractmethod
    async def create_category(self, *, write: FinanceCategoryCreation) -> FinanceMonth: ...

    @abstractmethod
    async def update_category(self, *, write: FinanceCategoryUpdate) -> FinanceMonth: ...

    @abstractmethod
    async def set_category_archived(self, *, write: FinanceCategoryArchival) -> FinanceMonth: ...

    @abstractmethod
    async def delete_category(self, *, write: FinanceCategoryDeletion) -> FinanceMonth: ...

    @abstractmethod
    async def list_transactions(
        self,
        *,
        owner_username: str,
        include_deleted: bool,
        now: datetime,
    ) -> list[FinanceTransaction]: ...

    @abstractmethod
    async def get_transaction(
        self,
        *,
        owner_username: str,
        transaction_id: str,
        now: datetime,
    ) -> FinanceTransaction: ...

    @abstractmethod
    async def create_transaction(
        self,
        *,
        write: FinanceTransactionCreation,
    ) -> FinanceTransaction: ...

    @abstractmethod
    async def update_transaction(
        self,
        *,
        write: FinanceTransactionUpdate,
    ) -> FinanceTransaction: ...

    @abstractmethod
    async def set_transaction_deleted(
        self,
        *,
        write: FinanceTransactionDeletionChange,
    ) -> FinanceTransaction: ...

    @abstractmethod
    async def revisions(
        self,
        *,
        owner_username: str,
        transaction_id: str,
        now: datetime,
    ) -> list[FinanceTransactionRevision]: ...

    @abstractmethod
    async def rate_for_date(self, *, on_date: date) -> tuple[str, FinanceRateSet] | None: ...

    @abstractmethod
    async def latest_rate_before_date(
        self,
        *,
        on_date: date,
    ) -> tuple[str, FinanceRateSet] | None: ...

    @abstractmethod
    async def save_rate_set(self, *, rate_set: FinanceRateSet) -> str: ...
