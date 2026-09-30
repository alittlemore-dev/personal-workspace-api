from dataclasses import dataclass
from datetime import date

from core.finance.clients import FinanceRateClient
from core.finance.enums import FinanceCurrency
from core.finance.exceptions import FinanceConflictError, FinanceRateUnavailableError
from core.finance.schemas import (
    ChangeFinanceCurrencyParams,
    CreateFinanceCategoryParams,
    CreateFinanceTransactionParams,
    DeleteFinanceCategoryParams,
    EnsureFinanceMonthParams,
    FinanceCategoryArchival,
    FinanceCategoryCreation,
    FinanceCategoryDeletion,
    FinanceCategoryUpdate,
    FinanceCurrencyChange,
    FinanceMonth,
    FinanceMonthParams,
    FinanceOpeningBalanceUpdate,
    FinanceRevisions,
    FinanceTransaction,
    FinanceTransactionCreation,
    FinanceTransactionDeletionChange,
    FinanceTransactionPricing,
    FinanceTransactionRevisionsParams,
    FinanceTransactions,
    FinanceTransactionUpdate,
    ListFinanceTransactionsParams,
    SetFinanceCategoryArchivedParams,
    SetFinanceTransactionDeletedParams,
    UpdateFinanceCategoryParams,
    UpdateFinanceTransactionParams,
    UpdateOpeningBalanceParams,
)
from core.finance.storages import FinanceStorage


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceUseCase:
    storage: FinanceStorage
    rate_client: FinanceRateClient

    async def ensure_month(self, params: EnsureFinanceMonthParams) -> FinanceMonth:
        tracker = await self.storage.lock_tracker(owner_username=params.owner_username)
        if tracker is None:
            tracker = await self.storage.create_tracker(
                owner_username=params.owner_username,
                time_zone=params.time_zone,
                now=params.now,
            )
        current_period = tracker.current_period(params.now)
        month = await self.storage.latest_month(tracker=tracker)
        if month is None:
            templates = await self.storage.templates(language=params.language)
            return await self.storage.create_initial_month(
                tracker=tracker,
                period_start=current_period,
                currency=FinanceCurrency.for_language(params.language),
                templates=templates,
                now=params.now,
            )
        archived_category_ids = await self.storage.archived_category_ids(tracker=tracker)
        while month.period_start < current_period:
            month = await self.storage.create_rollover_month(
                tracker=tracker,
                rollover=month.rollover(archived_category_ids),
                now=params.now,
            )
        if month.period_start != current_period:
            raise FinanceConflictError
        return month

    async def get_month(self, params: FinanceMonthParams) -> FinanceMonth:
        return await self.storage.get_month(owner_username=params.owner_username, now=params.now)

    async def update_opening_balance(self, params: UpdateOpeningBalanceParams) -> FinanceMonth:
        month = await self.storage.lock_month(owner_username=params.owner_username, now=params.now)
        params.amount.validate_precision(month.currency)
        return await self.storage.update_opening_balance(
            write=FinanceOpeningBalanceUpdate(month=month, params=params),
        )

    async def change_currency(self, params: ChangeFinanceCurrencyParams) -> FinanceMonth:
        month = await self.storage.get_month(owner_username=params.owner_username, now=params.now)
        if month.currency == params.currency:
            return month
        on_date = params.now.astimezone(month.time_zone).date()
        rate_set_id = await self.resolve_rate_set_id(on_date=on_date)
        month = await self.storage.lock_month(owner_username=params.owner_username, now=params.now)
        if month.currency == params.currency:
            return month
        rate_set = await self.storage.get_rate_set(rate_set_id=rate_set_id)
        return await self.storage.apply_currency_change(
            change=FinanceCurrencyChange(
                month_id=month.id,
                time_zone=month.time_zone,
                previous_currency=month.currency,
                new_currency=params.currency,
                rate_set_id=rate_set_id,
                before=month.amount_snapshot(),
                after=month.convert_amounts(
                    params.currency,
                    rate_set.conversion_factor(month.currency, params.currency),
                ),
                actor_username=params.owner_username,
                now=params.now,
            ),
        )

    async def create_category(self, params: CreateFinanceCategoryParams) -> FinanceMonth:
        month = await self.storage.lock_month(owner_username=params.owner_username, now=params.now)
        params.validate(month.currency)
        month.check_category_name(params.kind, params.name, None)
        return await self.storage.create_category(
            write=FinanceCategoryCreation(
                month=month,
                params=params,
                position=month.next_category_position(params.kind),
            ),
        )

    async def update_category(self, params: UpdateFinanceCategoryParams) -> FinanceMonth:
        month = await self.storage.lock_month(owner_username=params.owner_username, now=params.now)
        params.validate(month.currency)
        category = month.get_category(params.category_id)
        category.check_active()
        month.check_category_name(category.kind, params.name, category.id)
        return await self.storage.update_category(
            write=FinanceCategoryUpdate(month=month, category=category, params=params),
        )

    async def set_category_archived(self, params: SetFinanceCategoryArchivedParams) -> FinanceMonth:
        month = await self.storage.lock_month(owner_username=params.owner_username, now=params.now)
        return await self.storage.set_category_archived(
            write=FinanceCategoryArchival(
                month=month,
                category=month.get_category(params.category_id),
                params=params,
            ),
        )

    async def list_transactions(self, params: ListFinanceTransactionsParams) -> FinanceTransactions:
        return FinanceTransactions(
            transactions=await self.storage.list_transactions(
                owner_username=params.owner_username,
                include_deleted=params.include_deleted,
                now=params.now,
            ),
        )

    async def delete_category(self, params: DeleteFinanceCategoryParams) -> FinanceMonth:
        month = await self.storage.lock_month(owner_username=params.owner_username, now=params.now)
        return await self.storage.delete_category(
            write=FinanceCategoryDeletion(
                month=month,
                category=month.get_category(params.category_id),
            ),
        )

    async def create_transaction(
        self,
        params: CreateFinanceTransactionParams,
    ) -> FinanceTransaction:
        month = await self.storage.get_month(owner_username=params.owner_username, now=params.now)
        zone = month.time_zone
        params.draft.validate(period_start=month.period_start, time_zone=zone)
        rate_set_id = await self.resolve_rate_set_id(
            on_date=params.draft.occurred_at.astimezone(zone).date(),
        )
        rate_set = await self.storage.get_rate_set(rate_set_id=rate_set_id)
        month = await self.storage.lock_month(owner_username=params.owner_username, now=params.now)
        category = month.get_category(params.draft.category_id)
        category.check_accepting_transaction(None)
        return await self.storage.create_transaction(
            write=FinanceTransactionCreation(
                month=month,
                category=category,
                params=params,
                pricing=FinanceTransactionPricing.from_draft(params.draft, rate_set_id, rate_set),
            ),
        )

    async def update_transaction(
        self,
        params: UpdateFinanceTransactionParams,
    ) -> FinanceTransaction:
        month = await self.storage.get_month(owner_username=params.owner_username, now=params.now)
        zone = month.time_zone
        params.draft.validate(period_start=month.period_start, time_zone=zone)
        existing = await self.storage.get_transaction(
            owner_username=params.owner_username,
            transaction_id=params.transaction_id,
            now=params.now,
        )
        existing.check_updatable(params.version)
        rate_set_id = (
            await self.resolve_rate_set_id(on_date=params.draft.occurred_at.astimezone(zone).date())
            if existing.has_monetary_change(params.draft, zone)
            else None
        )
        pricing = (
            FinanceTransactionPricing.from_draft(
                params.draft,
                rate_set_id,
                await self.storage.get_rate_set(rate_set_id=rate_set_id),
            )
            if rate_set_id is not None
            else None
        )
        month = await self.storage.lock_month(owner_username=params.owner_username, now=params.now)
        existing = await self.storage.get_transaction(
            owner_username=params.owner_username,
            transaction_id=params.transaction_id,
            now=params.now,
        )
        existing.check_updatable(params.version)
        category = month.get_category(params.draft.category_id)
        category.check_accepting_transaction(existing.category_id)
        return await self.storage.update_transaction(
            write=FinanceTransactionUpdate(
                month=month,
                category=category,
                transaction=existing,
                params=params,
                pricing=pricing,
            ),
        )

    async def set_transaction_deleted(
        self,
        params: SetFinanceTransactionDeletedParams,
    ) -> FinanceTransaction:
        month = await self.storage.lock_month(owner_username=params.owner_username, now=params.now)
        existing = await self.storage.get_transaction(
            owner_username=params.owner_username,
            transaction_id=params.transaction_id,
            now=params.now,
        )
        existing.check_deletion_change(params.version, deleted=params.deleted)
        return await self.storage.set_transaction_deleted(
            write=FinanceTransactionDeletionChange(
                month=month,
                transaction=existing,
                params=params,
            ),
        )

    async def revisions(self, params: FinanceTransactionRevisionsParams) -> FinanceRevisions:
        return FinanceRevisions(
            revisions=await self.storage.revisions(
                owner_username=params.owner_username,
                transaction_id=params.transaction_id,
                now=params.now,
            ),
        )

    async def resolve_rate_set_id(self, *, on_date: date) -> str:
        cached = await self.storage.rate_for_date(on_date=on_date)
        if cached is not None:
            return cached[0]
        try:
            rate_set = await self.rate_client.fetch(on_date=on_date)
        except FinanceRateUnavailableError:
            eligible = await self.storage.latest_rate_before_date(on_date=on_date)
            if eligible is None:
                raise
            return eligible[0]
        return await self.storage.save_rate_set(rate_set=rate_set)

    async def refresh_rates(self, *, on_date: date) -> None:
        rate_set = await self.rate_client.fetch(on_date=on_date)
        await self.storage.save_rate_set(rate_set=rate_set)
