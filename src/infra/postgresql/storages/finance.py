from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.finance.enums import FinanceCurrency, FinanceKind, FinanceRevisionAction
from core.finance.exceptions import (
    FinanceConflictError,
    FinanceNotFoundError,
    InvalidFinanceDataError,
)
from core.finance.schemas import (
    Amount,
    FinanceActuals,
    FinanceCategoryArchival,
    FinanceCategoryCreation,
    FinanceCategoryDeletion,
    FinanceCategoryName,
    FinanceCategorySnapshot,
    FinanceCategoryUpdate,
    FinanceCurrencyChange,
    FinanceMonth,
    FinanceMonthRollover,
    FinanceMonthSnapshot,
    FinanceOpeningBalanceUpdate,
    FinanceRateSet,
    FinanceTemplateCategory,
    FinanceTracker,
    FinanceTransaction,
    FinanceTransactionCreation,
    FinanceTransactionDeletionChange,
    FinanceTransactionPricing,
    FinanceTransactionRevision,
    FinanceTransactionUpdate,
)
from core.finance.storages import FinanceStorage
from core.i18n.enums import LanguageEnum
from infra.postgresql.models.finance import (
    FinanceCategoryModel,
    FinanceMonthCategoryModel,
    FinanceMonthCurrencyChangeModel,
    FinanceMonthModel,
    FinanceRateModel,
    FinanceRateSetModel,
    FinanceTemplateCategoryModel,
    FinanceTrackerModel,
    FinanceTransactionModel,
    FinanceTransactionRevisionModel,
)
from infra.postgresql.schemas.finance import (
    FinanceMonthCurrencySnapshotSchema,
    FinanceTransactionSnapshotSchema,
)


@dataclass(kw_only=True)
class FinanceDatabaseStorage(FinanceStorage):
    session: AsyncSession

    async def _tracker(self, owner_username: str) -> FinanceTrackerModel:
        tracker = await self.session.scalar(
            select(FinanceTrackerModel)
            .where(FinanceTrackerModel.owner_username == owner_username)
            .execution_options(populate_existing=True),
        )
        if tracker is None:
            raise FinanceNotFoundError
        return tracker

    async def _month(
        self,
        owner_username: str,
        now: datetime,
    ) -> tuple[FinanceTrackerModel, FinanceMonthModel]:
        tracker = await self._tracker(owner_username)
        local = now.astimezone(tracker.time_zone)
        period = date(local.year, local.month, 1)
        month = await self.session.scalar(
            select(FinanceMonthModel)
            .where(
                FinanceMonthModel.tracker_id == tracker.id,
                FinanceMonthModel.period_start == period,
            )
            .execution_options(populate_existing=True),
        )
        if month is None:
            raise FinanceNotFoundError
        return tracker, month

    async def _actuals(
        self,
        month: FinanceMonthModel | FinanceMonth,
    ) -> tuple[Decimal, Decimal, dict[str, Decimal]]:
        rows = await self.session.execute(
            select(FinanceTransactionModel, FinanceRateModel)
            .join(
                FinanceRateModel,
                (FinanceRateModel.rate_set_id == FinanceTransactionModel.rate_set_id)
                & (FinanceRateModel.currency == month.currency),
            )
            .where(
                FinanceTransactionModel.month_id == month.id,
                FinanceTransactionModel.deleted_at.is_(None),
            )
            .execution_options(populate_existing=True),
        )
        income = Decimal(0)
        expense = Decimal(0)
        by_category: dict[str, Decimal] = {}
        for transaction, rate in rows:
            value = transaction.amount_rub / rate.rub_per_unit
            if transaction.month_category_id is not None:
                category_id = transaction.month_category_id
                by_category[category_id] = by_category.get(category_id, Decimal(0)) + value
            if transaction.kind == FinanceKind.INCOME:
                income += value
            else:
                expense += value
        return income, expense, by_category

    async def _locked_month(
        self,
        owner_username: str,
        now: datetime,
    ) -> tuple[FinanceTrackerModel, FinanceMonthModel]:
        await self.session.execute(
            select(func.pg_advisory_xact_lock(func.hashtext(owner_username))),
        )
        return await self._month(owner_username, now)

    async def _view(
        self,
        tracker: FinanceTrackerModel | FinanceTracker,
        month: FinanceMonthModel | FinanceMonth,
    ) -> FinanceMonth:
        income, expense, by_category = await self._actuals(month)
        categories = list(
            await self.session.scalars(
                select(FinanceMonthCategoryModel)
                .where(FinanceMonthCategoryModel.month_id == month.id)
                .order_by(
                    FinanceMonthCategoryModel.kind,
                    FinanceMonthCategoryModel.position,
                    FinanceMonthCategoryModel.id,
                )
                .execution_options(populate_existing=True),
            ),
        )

        return FinanceMonth.compose(
            FinanceMonthSnapshot(
                id=month.id,
                tracker_id=month.tracker_id,
                period_start=month.period_start,
                time_zone=tracker.time_zone,
                currency=month.currency,
                opening_balance=Amount(month.opening_balance),
                categories=[
                    FinanceCategorySnapshot(
                        id=category.id,
                        stable_id=category.category_id,
                        kind=category.kind,
                        name=FinanceCategoryName(category.name),
                        planned_amount=Amount(category.planned_amount)
                        if category.planned_amount is not None
                        else None,
                        position=category.position,
                        archived=not category.accepting_transactions,
                    )
                    for category in categories
                ],
            ),
            FinanceActuals(
                income=Amount(income),
                expense=Amount(expense),
                by_category={
                    category_id: Amount(value) for category_id, value in by_category.items()
                },
            ),
        )

    async def lock_tracker(self, *, owner_username: str) -> FinanceTracker | None:
        await self.session.execute(
            select(func.pg_advisory_xact_lock(func.hashtext(owner_username))),
        )
        model = await self.session.scalar(
            select(FinanceTrackerModel)
            .where(FinanceTrackerModel.owner_username == owner_username)
            .execution_options(populate_existing=True),
        )
        return FinanceTracker(id=model.id, time_zone=model.time_zone) if model is not None else None

    async def create_tracker(
        self,
        *,
        owner_username: str,
        time_zone: ZoneInfo,
        now: datetime,
    ) -> FinanceTracker:
        model = FinanceTrackerModel(
            owner_username=owner_username,
            time_zone=time_zone,
            created_at=now,
        )
        self.session.add(model)
        await self.session.flush()
        return FinanceTracker(id=model.id, time_zone=model.time_zone)

    async def latest_month(self, *, tracker: FinanceTracker) -> FinanceMonth | None:
        model = await self.session.scalar(
            select(FinanceMonthModel)
            .where(FinanceMonthModel.tracker_id == tracker.id)
            .order_by(FinanceMonthModel.period_start.desc())
            .limit(1)
            .execution_options(populate_existing=True),
        )
        return await self._view(tracker, model) if model is not None else None

    async def archived_category_ids(self, *, tracker: FinanceTracker) -> set[str]:
        return set(
            await self.session.scalars(
                select(FinanceCategoryModel.id).where(
                    FinanceCategoryModel.tracker_id == tracker.id,
                    FinanceCategoryModel.archived_at.is_not(None),
                ),
            ),
        )

    async def templates(self, *, language: LanguageEnum) -> list[FinanceTemplateCategory]:
        rows = await self.session.scalars(
            select(FinanceTemplateCategoryModel).order_by(
                FinanceTemplateCategoryModel.kind,
                FinanceTemplateCategoryModel.position,
            ),
        )
        return [
            FinanceTemplateCategory(
                kind=row.kind,
                name=FinanceCategoryName(
                    row.name_ru if language == LanguageEnum.RU else row.name_en,
                ),
                position=row.position,
            )
            for row in rows
        ]

    async def create_initial_month(
        self,
        *,
        tracker: FinanceTracker,
        period_start: date,
        currency: FinanceCurrency,
        templates: list[FinanceTemplateCategory],
        now: datetime,
    ) -> FinanceMonth:
        month = FinanceMonthModel(
            tracker_id=tracker.id,
            period_start=period_start,
            currency=currency,
            opening_balance=Amount(0),
            previous_month_id=None,
            transferred_balance=None,
            version=1,
            created_at=now,
        )
        self.session.add(month)
        await self.session.flush()
        for template in templates:
            stable = FinanceCategoryModel(
                tracker_id=tracker.id,
                kind=template.kind,
                archived_at=None,
                created_at=now,
            )
            self.session.add(stable)
            await self.session.flush()
            self.session.add(
                FinanceMonthCategoryModel(
                    month_id=month.id,
                    category_id=stable.id,
                    kind=template.kind,
                    name=template.name,
                    normalized_name=template.name.normalized,
                    planned_amount=None,
                    position=template.position,
                    accepting_transactions=True,
                    source_month_category_id=None,
                ),
            )
        await self.session.flush()
        return await self._view(tracker, month)

    async def create_rollover_month(
        self,
        *,
        tracker: FinanceTracker,
        rollover: FinanceMonthRollover,
        now: datetime,
    ) -> FinanceMonth:
        month = FinanceMonthModel(
            tracker_id=tracker.id,
            period_start=rollover.period_start,
            currency=rollover.currency,
            opening_balance=rollover.opening_balance,
            previous_month_id=rollover.previous_month_id,
            transferred_balance=rollover.opening_balance,
            version=1,
            created_at=now,
        )
        self.session.add(month)
        await self.session.flush()
        self.session.add_all(
            FinanceMonthCategoryModel(
                month_id=month.id,
                category_id=category.stable_id,
                kind=category.kind,
                name=category.name,
                normalized_name=category.name.normalized,
                planned_amount=category.planned_amount,
                position=category.position,
                accepting_transactions=True,
                source_month_category_id=category.id,
            )
            for category in rollover.categories
        )
        await self.session.flush()
        return await self._view(tracker, month)

    async def get_month(self, *, owner_username: str, now: datetime) -> FinanceMonth:
        tracker, month = await self._month(owner_username, now)
        return await self._view(tracker, month)

    async def lock_month(self, *, owner_username: str, now: datetime) -> FinanceMonth:
        tracker, month = await self._locked_month(owner_username, now)
        return await self._view(tracker, month)

    async def update_opening_balance(
        self,
        *,
        write: FinanceOpeningBalanceUpdate,
    ) -> FinanceMonth:
        month = await self.session.scalar(
            update(FinanceMonthModel)
            .where(FinanceMonthModel.id == write.month.id)
            .values(
                opening_balance=write.params.amount,
                version=FinanceMonthModel.version + 1,
            )
            .returning(FinanceMonthModel)
            .execution_options(populate_existing=True),
        )
        if month is None:
            raise FinanceNotFoundError
        return await self._view(
            FinanceTracker(id=write.month.tracker_id, time_zone=write.month.time_zone),
            month,
        )

    async def apply_currency_change(self, *, change: FinanceCurrencyChange) -> FinanceMonth:
        month = await self.session.scalar(
            update(FinanceMonthModel)
            .where(FinanceMonthModel.id == change.month_id)
            .values(
                currency=change.new_currency,
                opening_balance=change.after.opening_balance,
                version=FinanceMonthModel.version + 1,
            )
            .returning(FinanceMonthModel)
            .execution_options(populate_existing=True),
        )
        if month is None:
            raise FinanceNotFoundError
        for category_id, amount in change.after.plans.items():
            await self.session.execute(
                update(FinanceMonthCategoryModel)
                .where(
                    FinanceMonthCategoryModel.id == category_id,
                    FinanceMonthCategoryModel.month_id == change.month_id,
                )
                .values(planned_amount=amount),
            )
        self.session.add(
            FinanceMonthCurrencyChangeModel(
                month_id=change.month_id,
                previous_currency=change.previous_currency,
                new_currency=change.new_currency,
                rate_set_id=change.rate_set_id,
                before_state=FinanceMonthCurrencySnapshotSchema(
                    opening_balance=str(change.before.opening_balance),
                    plans={
                        category_id: str(amount)
                        for category_id, amount in change.before.plans.items()
                    },
                ),
                after_state=FinanceMonthCurrencySnapshotSchema(
                    opening_balance=str(change.after.opening_balance),
                    plans={
                        category_id: str(amount)
                        for category_id, amount in change.after.plans.items()
                    },
                ),
                actor_username=change.actor_username,
                changed_at=change.now,
            ),
        )
        await self.session.flush()
        return await self._view(
            FinanceTracker(id=month.tracker_id, time_zone=change.time_zone),
            month,
        )

    async def create_category(
        self,
        *,
        write: FinanceCategoryCreation,
    ) -> FinanceMonth:
        stable = FinanceCategoryModel(
            tracker_id=write.month.tracker_id,
            kind=write.params.kind,
            archived_at=None,
            created_at=write.params.now,
        )
        self.session.add(stable)
        await self.session.flush()
        self.session.add(
            FinanceMonthCategoryModel(
                month_id=write.month.id,
                category_id=stable.id,
                kind=write.params.kind,
                name=write.params.name,
                normalized_name=write.params.name.normalized,
                planned_amount=write.params.planned_amount,
                position=write.position,
                accepting_transactions=True,
                source_month_category_id=None,
            ),
        )
        await self.session.flush()
        return await self._view(
            FinanceTracker(id=write.month.tracker_id, time_zone=write.month.time_zone),
            write.month,
        )

    async def update_category(
        self,
        *,
        write: FinanceCategoryUpdate,
    ) -> FinanceMonth:
        category_id = await self.session.scalar(
            update(FinanceMonthCategoryModel)
            .where(
                FinanceMonthCategoryModel.id == write.category.id,
                FinanceMonthCategoryModel.month_id == write.month.id,
            )
            .values(
                name=write.params.name,
                normalized_name=write.params.name.normalized,
                planned_amount=write.params.planned_amount,
                position=write.params.position,
            )
            .returning(FinanceMonthCategoryModel.id),
        )
        if category_id is None:
            raise FinanceNotFoundError
        return await self._view(
            FinanceTracker(id=write.month.tracker_id, time_zone=write.month.time_zone),
            write.month,
        )

    async def set_category_archived(
        self,
        *,
        write: FinanceCategoryArchival,
    ) -> FinanceMonth:
        category_id = await self.session.scalar(
            update(FinanceMonthCategoryModel)
            .where(
                FinanceMonthCategoryModel.id == write.category.id,
                FinanceMonthCategoryModel.month_id == write.month.id,
            )
            .values(accepting_transactions=not write.params.archived)
            .returning(FinanceMonthCategoryModel.id),
        )
        if category_id is None:
            raise FinanceNotFoundError
        await self.session.execute(
            update(FinanceCategoryModel)
            .where(
                FinanceCategoryModel.id == write.category.stable_id,
                FinanceCategoryModel.tracker_id == write.month.tracker_id,
            )
            .values(archived_at=write.params.now if write.params.archived else None),
        )
        return await self._view(
            FinanceTracker(id=write.month.tracker_id, time_zone=write.month.time_zone),
            write.month,
        )

    async def delete_category(
        self,
        *,
        write: FinanceCategoryDeletion,
    ) -> FinanceMonth:
        snapshots = (
            select(FinanceMonthCategoryModel.id)
            .join(FinanceMonthModel)
            .where(
                FinanceMonthCategoryModel.category_id == write.category.stable_id,
                FinanceMonthModel.tracker_id == write.month.tracker_id,
            )
        )
        await self.session.execute(
            update(FinanceTransactionModel)
            .where(FinanceTransactionModel.month_category_id.in_(snapshots))
            .values(month_category_id=None)
            .execution_options(synchronize_session="fetch"),
        )
        await self.session.execute(
            update(FinanceMonthCategoryModel)
            .where(FinanceMonthCategoryModel.source_month_category_id.in_(snapshots))
            .values(source_month_category_id=None)
            .execution_options(synchronize_session="fetch"),
        )
        await self.session.execute(
            delete(FinanceMonthCategoryModel)
            .where(FinanceMonthCategoryModel.id.in_(snapshots))
            .execution_options(synchronize_session="fetch"),
        )
        stable_id = await self.session.scalar(
            delete(FinanceCategoryModel)
            .where(
                FinanceCategoryModel.id == write.category.stable_id,
                FinanceCategoryModel.tracker_id == write.month.tracker_id,
            )
            .returning(FinanceCategoryModel.id),
        )
        if stable_id is None:
            raise FinanceNotFoundError
        return await self._view(
            FinanceTracker(id=write.month.tracker_id, time_zone=write.month.time_zone),
            write.month,
        )

    async def rate_for_date(self, *, on_date: date) -> tuple[str, FinanceRateSet] | None:
        model = await self.session.scalar(
            select(FinanceRateSetModel)
            .where(FinanceRateSetModel.effective_on == on_date)
            .order_by(
                FinanceRateSetModel.effective_on.desc(),
                FinanceRateSetModel.fetched_at.desc(),
            )
            .limit(1),
        )
        if model is None:
            return None
        return await self._rate_set_view(model)

    async def latest_rate_before_date(self, *, on_date: date) -> tuple[str, FinanceRateSet] | None:
        model = await self.session.scalar(
            select(FinanceRateSetModel)
            .where(FinanceRateSetModel.effective_on <= on_date)
            .order_by(
                FinanceRateSetModel.effective_on.desc(),
                FinanceRateSetModel.fetched_at.desc(),
            )
            .limit(1),
        )
        if model is None:
            return None
        return await self._rate_set_view(model)

    async def get_rate_set(self, *, rate_set_id: str) -> FinanceRateSet:
        model = await self.session.get(FinanceRateSetModel, rate_set_id)
        if model is None:
            raise FinanceNotFoundError
        result = await self._rate_set_view(model)
        if result is None:
            raise InvalidFinanceDataError
        return result[1]

    async def _rate_set_view(self, model: FinanceRateSetModel) -> tuple[str, FinanceRateSet] | None:
        rows = list(
            await self.session.scalars(
                select(FinanceRateModel).where(FinanceRateModel.rate_set_id == model.id),
            ),
        )
        rates = {rate.currency: rate.rub_per_unit for rate in rows}
        if set(rates) != set(FinanceCurrency):
            return None
        return model.id, FinanceRateSet(
            effective_on=model.effective_on,
            fetched_at=model.fetched_at,
            rates=rates,
            nominals={rate.currency: rate.nominal for rate in rows},
            payload_hash=model.payload_hash,
        )

    async def save_rate_set(self, *, rate_set: FinanceRateSet) -> str:
        statement = (
            insert(FinanceRateSetModel)
            .values(
                provider="cbr",
                effective_on=rate_set.effective_on,
                fetched_at=rate_set.fetched_at,
                payload_hash=rate_set.payload_hash,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    FinanceRateSetModel.provider,
                    FinanceRateSetModel.effective_on,
                    FinanceRateSetModel.payload_hash,
                ],
            )
        )
        await self.session.execute(statement)
        model = await self.session.scalar(
            select(FinanceRateSetModel).where(
                FinanceRateSetModel.provider == "cbr",
                FinanceRateSetModel.effective_on == rate_set.effective_on,
                FinanceRateSetModel.payload_hash == rate_set.payload_hash,
            ),
        )
        if model is None:
            raise FinanceConflictError
        for currency, value in rate_set.rates.items():
            await self.session.execute(
                insert(FinanceRateModel)
                .values(
                    rate_set_id=model.id,
                    currency=currency,
                    nominal=rate_set.nominals[currency],
                    rub_per_unit=value,
                )
                .on_conflict_do_nothing(
                    index_elements=[FinanceRateModel.rate_set_id, FinanceRateModel.currency],
                ),
            )
        await self.session.flush()
        return model.id

    async def _transaction_rows(
        self,
        month: FinanceMonthModel | FinanceMonth,
        *,
        include_deleted: bool,
    ) -> list[
        tuple[
            FinanceTransactionModel,
            FinanceMonthCategoryModel | None,
            FinanceRateSetModel,
            FinanceRateModel,
        ]
    ]:
        query = (
            select(
                FinanceTransactionModel,
                FinanceMonthCategoryModel,
                FinanceRateSetModel,
                FinanceRateModel,
            )
            .outerjoin(
                FinanceMonthCategoryModel,
                FinanceMonthCategoryModel.id == FinanceTransactionModel.month_category_id,
            )
            .join(
                FinanceRateSetModel,
                FinanceRateSetModel.id == FinanceTransactionModel.rate_set_id,
            )
            .join(
                FinanceRateModel,
                (FinanceRateModel.rate_set_id == FinanceRateSetModel.id)
                & (FinanceRateModel.currency == month.currency),
            )
            .where(FinanceTransactionModel.month_id == month.id)
            .order_by(FinanceTransactionModel.occurred_at.desc(), FinanceTransactionModel.id.desc())
            .execution_options(populate_existing=True)
        )
        if not include_deleted:
            query = query.where(FinanceTransactionModel.deleted_at.is_(None))
        return [tuple(row) for row in (await self.session.execute(query)).all()]

    def _transaction_view(
        self,
        model: FinanceTransactionModel,
        category: FinanceMonthCategoryModel | None,
        rate_set: FinanceRateSetModel,
        display_rate: FinanceRateModel,
        month_currency: FinanceCurrency,
    ) -> FinanceTransaction:
        return FinanceTransaction(
            id=model.id,
            source=model.source,
            author_id=model.author_id,
            author_label=model.author_label,
            category_id=model.month_category_id,
            category_name=category.name if category is not None else "",
            kind=model.kind,
            amount=Amount(model.original_amount),
            currency=model.original_currency,
            converted_amount=Amount(model.amount_rub / display_rate.rub_per_unit).rounded(
                month_currency,
            ),
            occurred_at=model.occurred_at,
            description=model.description,
            rate_effective_on=rate_set.effective_on,
            version=model.version,
            deleted=model.deleted_at is not None,
            pricing=FinanceTransactionPricing(
                rate_set_id=model.rate_set_id,
                amount_rub=Amount(model.amount_rub),
            ),
        )

    async def list_transactions(
        self,
        *,
        owner_username: str,
        include_deleted: bool,
        now: datetime,
    ) -> list[FinanceTransaction]:
        _, month = await self._month(owner_username, now)
        return [
            self._transaction_view(transaction, category, rate_set, rate, month.currency)
            for transaction, category, rate_set, rate in await self._transaction_rows(
                month,
                include_deleted=include_deleted,
            )
        ]

    async def get_transaction(
        self,
        *,
        owner_username: str,
        transaction_id: str,
        now: datetime,
    ) -> FinanceTransaction:
        _, month = await self._month(owner_username, now)
        return await self._transaction_view_by_id(month, transaction_id)

    async def _transaction_view_by_id(
        self,
        month: FinanceMonthModel | FinanceMonth,
        transaction_id: str,
    ) -> FinanceTransaction:
        rows = await self._transaction_rows(month, include_deleted=True)
        for transaction, category, rate_set, rate in rows:
            if transaction.id == transaction_id:
                return self._transaction_view(transaction, category, rate_set, rate, month.currency)
        raise FinanceNotFoundError

    async def confirmed_operation(
        self,
        *,
        owner_username: str,
        author_id: str,
        operation_id: str,
    ) -> FinanceTransaction | None:
        month = await self.session.scalar(
            select(FinanceMonthModel)
            .join(FinanceTrackerModel)
            .join(FinanceTransactionModel)
            .where(
                FinanceTrackerModel.owner_username == owner_username,
                FinanceTransactionModel.author_id == author_id,
                FinanceTransactionModel.operation_id == operation_id,
            )
            .execution_options(populate_existing=True),
        )
        if month is None:
            return None
        transaction_id = await self.session.scalar(
            select(FinanceTransactionModel.id).where(
                FinanceTransactionModel.month_id == month.id,
                FinanceTransactionModel.operation_id == operation_id,
                FinanceTransactionModel.author_id == author_id,
            ),
        )
        if transaction_id is None:
            return None
        return await self._transaction_view_by_id(month, transaction_id)

    async def create_transaction(
        self,
        *,
        write: FinanceTransactionCreation,
    ) -> FinanceTransaction:
        model = FinanceTransactionModel(
            month_id=write.month.id,
            month_category_id=write.category.id,
            kind=write.category.kind,
            original_amount=write.params.draft.amount,
            original_currency=write.params.draft.currency,
            amount_rub=write.pricing.amount_rub,
            rate_set_id=write.pricing.rate_set_id,
            occurred_at=write.params.draft.occurred_at,
            description=write.params.draft.description,
            author_username=write.params.owner_username,
            source=write.params.actor.source,
            author_id=write.params.actor.identifier,
            author_label=write.params.actor.label,
            operation_id=write.params.actor.operation_id,
            version=1,
            deleted_at=None,
            created_at=write.params.now,
            updated_at=write.params.now,
        )
        self.session.add(model)
        await self.session.flush()
        return await self._transaction_view_by_id(write.month, model.id)

    async def _owned_transaction(
        self,
        month: FinanceMonthModel,
        transaction_id: str,
    ) -> FinanceTransactionModel:
        model = await self.session.scalar(
            select(FinanceTransactionModel)
            .where(
                FinanceTransactionModel.id == transaction_id,
                FinanceTransactionModel.month_id == month.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True),
        )
        if model is None:
            raise FinanceNotFoundError
        return model

    def _revision(
        self,
        transaction: FinanceTransaction,
        action: FinanceRevisionAction,
        owner_username: str,
        now: datetime,
    ) -> FinanceTransactionRevisionModel:
        return FinanceTransactionRevisionModel(
            transaction_id=transaction.id,
            number=transaction.version,
            action=action,
            previous_state=FinanceTransactionSnapshotSchema.from_domain_schema(
                transaction.snapshot(),
            ),
            actor_username=owner_username,
            changed_at=now,
        )

    async def update_transaction(
        self,
        *,
        write: FinanceTransactionUpdate,
    ) -> FinanceTransaction:
        pricing = write.pricing if write.pricing is not None else write.transaction.pricing
        transaction_id = await self.session.scalar(
            update(FinanceTransactionModel)
            .where(
                FinanceTransactionModel.id == write.transaction.id,
                FinanceTransactionModel.month_id == write.month.id,
                FinanceTransactionModel.version == write.params.version,
                FinanceTransactionModel.deleted_at.is_(None),
            )
            .values(
                month_category_id=write.category.id,
                kind=write.category.kind,
                original_amount=write.params.draft.amount,
                original_currency=write.params.draft.currency,
                amount_rub=pricing.amount_rub,
                rate_set_id=pricing.rate_set_id,
                occurred_at=write.params.draft.occurred_at,
                description=write.params.draft.description,
                version=FinanceTransactionModel.version + 1,
                updated_at=write.params.now,
            )
            .returning(FinanceTransactionModel.id),
        )
        if transaction_id is None:
            raise FinanceConflictError
        self.session.add(
            self._revision(
                write.transaction,
                FinanceRevisionAction.UPDATE,
                write.params.owner_username,
                write.params.now,
            ),
        )
        await self.session.flush()
        return await self._transaction_view_by_id(write.month, transaction_id)

    async def set_transaction_deleted(
        self,
        *,
        write: FinanceTransactionDeletionChange,
    ) -> FinanceTransaction:
        transaction_id = await self.session.scalar(
            update(FinanceTransactionModel)
            .where(
                FinanceTransactionModel.id == write.transaction.id,
                FinanceTransactionModel.month_id == write.month.id,
                FinanceTransactionModel.version == write.params.version,
            )
            .values(
                deleted_at=write.params.now if write.params.deleted else None,
                version=FinanceTransactionModel.version + 1,
                updated_at=write.params.now,
            )
            .returning(FinanceTransactionModel.id),
        )
        if transaction_id is None:
            raise FinanceConflictError
        self.session.add(
            self._revision(
                write.transaction,
                write.action,
                write.params.owner_username,
                write.params.now,
            ),
        )
        await self.session.flush()
        return await self._transaction_view_by_id(write.month, transaction_id)

    async def revisions(
        self,
        *,
        owner_username: str,
        transaction_id: str,
        now: datetime,
    ) -> list[FinanceTransactionRevision]:
        _, month = await self._month(owner_username, now)
        await self._owned_transaction(month, transaction_id)
        rows = await self.session.scalars(
            select(FinanceTransactionRevisionModel)
            .where(FinanceTransactionRevisionModel.transaction_id == transaction_id)
            .order_by(FinanceTransactionRevisionModel.number.desc()),
        )
        return [
            FinanceTransactionRevision(
                number=row.number,
                action=row.action,
                previous_state=row.previous_state.to_domain_schema(),
                actor_username=row.actor_username,
                changed_at=row.changed_at,
            )
            for row in rows
        ]
