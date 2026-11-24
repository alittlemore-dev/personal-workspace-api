from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.finance.assets.analytics_use_cases import AssetAnalyticsStorage
from core.finance.assets.goals import AssetGoal, AssetGoalParams, SetAssetGoalParams
from core.finance.assets.reports import (
    OBSERVATION_MONTHS,
    AssetIncome,
    AssetReportFacts,
    AssetReportParams,
)
from core.finance.assets.valuation import AssetRate, AssetRates
from core.finance.enums import FinanceKind
from infra.postgresql.models.finance import (
    FinanceCategoryModel,
    FinanceMonthCategoryModel,
    FinanceMonthModel,
    FinanceRateModel,
    FinanceRateSetModel,
    FinanceTrackerModel,
    FinanceTransactionModel,
)
from infra.postgresql.models.finance_asset_analytics import AssetGoalModel


@dataclass(kw_only=True)
class FinanceAssetAnalyticsStorage(AssetAnalyticsStorage):
    session: AsyncSession

    async def lock_owner(self, *, owner_username: str, writing: bool) -> None:
        lock = func.pg_advisory_xact_lock if writing else func.pg_advisory_xact_lock_shared
        await self.session.execute(select(lock(func.hashtext(owner_username))))

    async def rates(self, *, end: date) -> AssetRates:
        result = await self.session.execute(
            select(FinanceRateSetModel, FinanceRateModel)
            .join(FinanceRateModel, FinanceRateModel.rate_set_id == FinanceRateSetModel.id)
            .where(FinanceRateSetModel.effective_on <= end)
            .order_by(
                FinanceRateSetModel.effective_on,
                FinanceRateSetModel.fetched_at,
                FinanceRateSetModel.id,
            ),
        )
        rates: dict[str, AssetRate] = {}
        for rate_set, rate in result:
            if rate_set.id not in rates:
                rates[rate_set.id] = AssetRate(
                    id=rate_set.id,
                    source=rate_set.provider,
                    on_date=rate_set.effective_on,
                    rates={},
                )
            rates[rate_set.id].rates[rate.currency] = rate.rub_per_unit
        return AssetRates(ordered=list(rates.values()))

    async def facts(self, params: AssetReportParams) -> AssetReportFacts:
        zone = await self.session.scalar(
            select(FinanceTrackerModel.time_zone).where(
                FinanceTrackerModel.owner_username == params.owner_username,
            ),
        ) or ZoneInfo("UTC")
        end = min(params.end, params.now.astimezone(zone).date())
        forecast_start = end.replace(day=1)
        for _ in range(OBSERVATION_MONTHS):
            if forecast_start > date.min:
                forecast_start = (forecast_start - timedelta(days=1)).replace(day=1)
        start = min(params.start, forecast_start)
        income_query = (
            select(
                FinanceTransactionModel.occurred_at,
                func.coalesce(
                    FinanceMonthCategoryModel.category_id,
                    FinanceTransactionModel.former_category_id,
                ),
                FinanceTransactionModel.amount_rub,
                FinanceRateModel.rub_per_unit,
            )
            .select_from(FinanceTransactionModel)
            .join(FinanceMonthModel, FinanceMonthModel.id == FinanceTransactionModel.month_id)
            .join(FinanceTrackerModel, FinanceTrackerModel.id == FinanceMonthModel.tracker_id)
            .outerjoin(
                FinanceMonthCategoryModel,
                FinanceMonthCategoryModel.id == FinanceTransactionModel.month_category_id,
            )
            .join(
                FinanceRateModel,
                (FinanceRateModel.rate_set_id == FinanceTransactionModel.rate_set_id)
                & (FinanceRateModel.currency == params.currency),
            )
            .where(
                FinanceTrackerModel.owner_username == params.owner_username,
                FinanceTransactionModel.kind == FinanceKind.INCOME,
                FinanceTransactionModel.deleted_at.is_(None),
                FinanceTransactionModel.occurred_at
                < datetime.combine(end + timedelta(days=1), time.min, zone).astimezone(UTC),
            )
        )
        if start != date.min:
            income_query = income_query.where(
                FinanceTransactionModel.occurred_at
                >= datetime.combine(start, time.min, zone).astimezone(UTC),
            )
        income_rows = await self.session.execute(income_query)
        goals = await self.session.scalars(
            select(AssetGoalModel)
            .where(
                AssetGoalModel.owner_username == params.owner_username,
                AssetGoalModel.month <= end,
            )
            .order_by(AssetGoalModel.month),
        )
        return AssetReportFacts(
            zone=zone,
            incomes=[
                AssetIncome(
                    on_date=occurred.astimezone(zone).date(),
                    category_id=category,
                    amount=rub / rate,
                )
                for occurred, category, rub, rate in income_rows
            ],
            goals=[self.domain_goal(row) for row in goals],
        )

    @staticmethod
    def domain_goal(row: AssetGoalModel) -> AssetGoal:
        return AssetGoal(
            month=row.month,
            percent=row.percent,
            all_income=row.all_income,
            category_ids=tuple(row.category_ids),
        )

    async def goal(self, params: AssetGoalParams) -> AssetGoal | None:
        row = await self.session.scalar(
            select(AssetGoalModel)
            .where(
                AssetGoalModel.owner_username == params.owner_username,
                AssetGoalModel.month <= params.month,
            )
            .order_by(AssetGoalModel.month.desc())
            .limit(1)
            .execution_options(populate_existing=True),
        )
        return self.domain_goal(row) if row else None

    async def income_categories(self, *, owner_username: str, ids: tuple[str, ...]) -> set[str]:
        return set(
            await self.session.scalars(
                select(FinanceCategoryModel.id)
                .join(
                    FinanceTrackerModel,
                    FinanceTrackerModel.id == FinanceCategoryModel.tracker_id,
                )
                .where(
                    FinanceTrackerModel.owner_username == owner_username,
                    FinanceCategoryModel.kind == FinanceKind.INCOME,
                    FinanceCategoryModel.id.in_(ids),
                ),
            ),
        )

    async def set_goal(self, params: SetAssetGoalParams) -> None:
        goal = params.goal
        insert_goal = insert(AssetGoalModel).values(
            owner_username=params.owner_username,
            month=goal.month,
            percent=goal.percent,
            all_income=goal.all_income,
            category_ids=list(goal.category_ids),
        )
        await self.session.execute(
            insert_goal.on_conflict_do_update(
                index_elements=[AssetGoalModel.owner_username, AssetGoalModel.month],
                set_={
                    "percent": insert_goal.excluded.percent,
                    "all_income": insert_goal.excluded.all_income,
                    "category_ids": insert_goal.excluded.category_ids,
                },
            ),
        )
