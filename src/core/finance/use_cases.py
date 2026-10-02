from dataclasses import dataclass, replace
from datetime import date, timedelta
from time import monotonic

from core.finance.clients import FinanceRateClient
from core.finance.enums import (
    FinanceCurrency,
    FinanceSource,
    FinanceStatisticsCurrency,
    FinanceStatisticsPeriod,
)
from core.finance.exceptions import (
    FinanceConflictError,
    FinanceRateUnavailableError,
)
from core.finance.schemas import (
    ChangeFinanceCurrencyParams,
    ConfirmedFinanceOperationParams,
    CreateFinanceCategoryParams,
    CreateFinanceTransactionParams,
    DeleteFinanceCategoryParams,
    EnsureFinanceMonthParams,
    FinanceCategoryArchival,
    FinanceCategoryCreation,
    FinanceCategoryDeletion,
    FinanceCategoryUpdate,
    FinanceCurrencyChange,
    FinanceHistoricalMonthParams,
    FinanceMonth,
    FinanceMonthParams,
    FinanceOpeningBalanceUpdate,
    FinanceRevisions,
    FinanceStatisticsComposition,
    FinanceStatisticsParams,
    FinanceStatisticsResult,
    FinanceStatisticsWindow,
    FinanceTransaction,
    FinanceTransactionCreation,
    FinanceTransactionDeletionChange,
    FinanceTransactionMonthParams,
    FinanceTransactionPricing,
    FinanceTransactionRevisionsParams,
    FinanceTransactions,
    FinanceTransactionUpdate,
    HistoricalFinanceRevisionsParams,
    ListFinanceTransactionsParams,
    ListHistoricalFinanceTransactionsParams,
    SetFinanceCategoryArchivedParams,
    SetFinanceTransactionDeletedParams,
    TelegramFinanceContextParams,
    UpdateFinanceCategoryParams,
    UpdateFinanceTransactionParams,
    UpdateOpeningBalanceParams,
)
from core.finance.services import (
    FinanceEventService,
    FinanceMonthService,
    FinanceStatisticsService,
    FinanceTelegramAccessService,
)
from core.finance.storages import FinanceStorage
from core.telegram.schemas import TelegramConnection


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceUseCase:
    storage: FinanceStorage
    rate_client: FinanceRateClient
    telegram_access: FinanceTelegramAccessService
    events: FinanceEventService
    months: FinanceMonthService
    statistics_service: FinanceStatisticsService

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
        return await self.months.advance(
            tracker=tracker,
            now=params.now,
        )

    async def telegram_context(
        self,
        params: TelegramFinanceContextParams,
    ) -> tuple[TelegramConnection, FinanceMonth | None]:
        connection = await self.telegram_access.resolve(params, lock=False)
        tracker = await self.storage.lock_tracker(owner_username=connection.owner_username)
        if tracker is None:
            return connection, None
        month = await self.months.advance(
            tracker=tracker,
            now=params.now,
        )
        return connection, month

    async def confirmed_telegram_operation(
        self,
        params: ConfirmedFinanceOperationParams,
    ) -> FinanceTransaction | None:
        await self.telegram_access.validate(
            actor=params.actor,
            owner_username=params.owner_username,
            now=params.now,
            lock=False,
        )
        return await self.storage.confirmed_operation(
            owner_username=params.owner_username,
            author_id=params.actor.identifier,
            operation_id=params.actor.operation_id,
        )

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
        started = monotonic()
        started_at = params.now
        if params.actor.source == FinanceSource.TELEGRAM:
            existing = await self.confirmed_telegram_operation(
                ConfirmedFinanceOperationParams(
                    actor=params.actor,
                    owner_username=params.owner_username,
                    now=params.now,
                ),
            )
            if existing is not None:
                return existing
        month = await self.months.for_transaction(
            FinanceTransactionMonthParams(
                owner_username=params.owner_username,
                now=params.now,
                period_start=params.period_start,
                lock=False,
            ),
        )
        zone = month.time_zone
        params.draft.validate(period_start=month.period_start, time_zone=zone)
        if params.actor.source == FinanceSource.TELEGRAM and month.id != params.actor.month_id:
            raise FinanceConflictError
        month.get_category(params.draft.category_id).check_accepting_transaction(None)
        rate_set_id = await self.resolve_rate_set_id(
            on_date=params.draft.occurred_at.astimezone(zone).date(),
        )
        rate_set = await self.storage.get_rate_set(rate_set_id=rate_set_id)
        if params.actor.source == FinanceSource.TELEGRAM:
            params = replace(params, now=started_at + timedelta(seconds=monotonic() - started))
        month = await self.months.for_transaction(
            FinanceTransactionMonthParams(
                owner_username=params.owner_username,
                now=params.now,
                period_start=params.period_start,
                lock=True,
            ),
        )
        if params.actor.source == FinanceSource.TELEGRAM:
            connection = await self.telegram_access.validate(
                actor=params.actor,
                owner_username=params.owner_username,
                now=params.now,
                lock=True,
            )
            existing = await self.storage.confirmed_operation(
                owner_username=params.owner_username,
                author_id=params.actor.identifier,
                operation_id=params.actor.operation_id,
            )
            if existing is not None:
                return existing
            params = replace(
                params,
                now=started_at + timedelta(seconds=monotonic() - started),
                actor=replace(params.actor, label=connection.label),
            )
            if month.id != params.actor.month_id or month.period_start != params.now.astimezone(
                month.time_zone,
            ).date().replace(day=1):
                raise FinanceConflictError
        params.draft.validate(period_start=month.period_start, time_zone=month.time_zone)
        category = month.get_category(params.draft.category_id)
        category.check_accepting_transaction(None)
        result = await self.storage.create_transaction(
            write=FinanceTransactionCreation(
                month=month,
                category=category,
                params=params,
                pricing=FinanceTransactionPricing.from_draft(params.draft, rate_set_id, rate_set),
            ),
        )
        after = await self.months.for_transaction(
            FinanceTransactionMonthParams(
                owner_username=params.owner_username,
                now=params.now,
                period_start=params.period_start,
                lock=False,
            ),
        )
        await self.events.created(
            owner_username=params.owner_username,
            before=month,
            after=after,
            transaction=result,
            now=params.now,
        )
        return result

    async def update_transaction(
        self,
        params: UpdateFinanceTransactionParams,
    ) -> FinanceTransaction:
        month = await self.months.for_transaction(
            FinanceTransactionMonthParams(
                owner_username=params.owner_username,
                now=params.now,
                period_start=params.period_start,
                lock=False,
            ),
        )
        zone = month.time_zone
        params.draft.validate(period_start=month.period_start, time_zone=zone)
        existing = await (
            self.storage.get_transaction(
                owner_username=params.owner_username,
                transaction_id=params.transaction_id,
                now=params.now,
            )
            if params.period_start is None
            else self.storage.transaction_for_period(
                owner_username=params.owner_username,
                transaction_id=params.transaction_id,
                period_start=month.period_start,
            )
        )
        existing.check_writable(month, params.now)
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
        month = await self.months.for_transaction(
            FinanceTransactionMonthParams(
                owner_username=params.owner_username,
                now=params.now,
                period_start=params.period_start,
                lock=True,
            ),
        )
        existing = await (
            self.storage.get_transaction(
                owner_username=params.owner_username,
                transaction_id=params.transaction_id,
                now=params.now,
            )
            if params.period_start is None
            else self.storage.transaction_for_period(
                owner_username=params.owner_username,
                transaction_id=params.transaction_id,
                period_start=month.period_start,
            )
        )
        existing.check_writable(month, params.now)
        existing.check_updatable(params.version)
        category = month.get_category(params.draft.category_id)
        category.check_accepting_transaction(existing.category_id)
        result = await self.storage.update_transaction(
            write=FinanceTransactionUpdate(
                month=month,
                category=category,
                transaction=existing,
                params=params,
                pricing=pricing,
            ),
        )
        after = await self.months.for_transaction(
            FinanceTransactionMonthParams(
                owner_username=params.owner_username,
                now=params.now,
                period_start=params.period_start,
                lock=False,
            ),
        )
        await self.events.changed(
            owner_username=params.owner_username,
            before=month,
            after=after,
            transaction=result,
            now=params.now,
        )
        return result

    async def set_transaction_deleted(
        self,
        params: SetFinanceTransactionDeletedParams,
    ) -> FinanceTransaction:
        month = await self.months.for_transaction(
            FinanceTransactionMonthParams(
                owner_username=params.owner_username,
                now=params.now,
                period_start=params.period_start,
                lock=True,
            ),
        )
        existing = await (
            self.storage.get_transaction(
                owner_username=params.owner_username,
                transaction_id=params.transaction_id,
                now=params.now,
            )
            if params.period_start is None
            else self.storage.transaction_for_period(
                owner_username=params.owner_username,
                transaction_id=params.transaction_id,
                period_start=month.period_start,
            )
        )
        existing.check_writable(month, params.now)
        existing.check_deletion_change(params.version, deleted=params.deleted)
        result = await self.storage.set_transaction_deleted(
            write=FinanceTransactionDeletionChange(
                month=month,
                transaction=existing,
                params=params,
            ),
        )
        after = await self.months.for_transaction(
            FinanceTransactionMonthParams(
                owner_username=params.owner_username,
                now=params.now,
                period_start=params.period_start,
                lock=False,
            ),
        )
        await self.events.changed(
            owner_username=params.owner_username,
            before=month,
            after=after,
            transaction=result,
            now=params.now,
        )
        return result

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

    async def historical_month(self, params: FinanceHistoricalMonthParams) -> FinanceMonth:
        current = await self.storage.get_month(owner_username=params.owner_username, now=params.now)
        params.check_period(current)
        return await self.storage.get_month_for_period(
            owner_username=params.owner_username,
            period_start=params.period_start,
        )

    async def historical_transactions(
        self,
        params: ListHistoricalFinanceTransactionsParams,
    ) -> FinanceTransactions:
        current = await self.storage.get_month(owner_username=params.owner_username, now=params.now)
        params.check_period(current)
        return FinanceTransactions(
            transactions=await self.storage.transactions_for_period(
                owner_username=params.owner_username,
                period_start=params.period_start,
                include_deleted=params.include_deleted,
            ),
        )

    async def historical_revisions(
        self,
        params: HistoricalFinanceRevisionsParams,
    ) -> FinanceRevisions:
        current = await self.storage.get_month(owner_username=params.owner_username, now=params.now)
        params.check_period(current)
        return FinanceRevisions(
            revisions=await self.storage.revisions_for_period(
                owner_username=params.owner_username,
                period_start=params.period_start,
                transaction_id=params.transaction_id,
            ),
        )

    async def statistics(self, params: FinanceStatisticsParams) -> FinanceStatisticsResult:
        month = await self.storage.get_month(owner_username=params.owner_username, now=params.now)
        window, previous_window = FinanceStatisticsWindow.for_period(
            params.period,
            params.now,
            month.time_zone,
        )
        budget_rate = None
        if params.period == FinanceStatisticsPeriod.THIS_MONTH and month.needs_budget_rate(
            params.currency,
        ):
            stored_rate = await self.storage.latest_rate_before_date(
                on_date=params.now.astimezone(month.time_zone).date(),
            )
            if stored_rate is None:
                raise FinanceRateUnavailableError
            budget_rate = await self.storage.get_rate_set(rate_set_id=stored_rate[0])
        source = await self.storage.statistics_source(
            owner_username=params.owner_username,
            start=previous_window.start,
            end=window.end,
            currency=None
            if params.currency == FinanceStatisticsCurrency.MONTH
            else FinanceCurrency(params.currency),
        )
        return self.statistics_service.compose_result(
            FinanceStatisticsComposition(
                params=params,
                month=month,
                window=window,
                previous_window=previous_window,
                source=source,
                budget_rate=budget_rate,
            ),
        )
