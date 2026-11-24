import asyncio
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.finance.assets.analytics_use_cases import AssetAnalyticsUseCase
from core.finance.assets.enums import AssetMovementKind as Kind
from core.finance.assets.enums import AssetPositionKind
from core.finance.assets.goals import AssetGoal, AssetGoalParams, SetAssetGoalParams
from core.finance.assets.reports import AssetReportParams
from core.finance.assets.schemas import AssetLocationDraft, AssetPositionDraft
from core.finance.enums import FinanceCurrency, FinanceKind
from core.finance.exceptions import FinanceNotFoundError
from core.finance.schemas import (
    CreateFinanceTransactionParams,
    DeleteFinanceCategoryParams,
    EnsureFinanceMonthParams,
    FinanceActor,
)
from core.i18n.enums import LanguageEnum
from infra.postgresql.storages.finance import FinanceDatabaseStorage
from infra.postgresql.storages.finance_asset_analytics import FinanceAssetAnalyticsStorage
from infra.postgresql.storages.finance_assets import AssetDatabaseStorage
from tests.helpers.factories.finance_assets import FinanceAssetFactory as Factory
from tests.test_cases import StorageTestCase


class TestFinanceAssetAnalytics(StorageTestCase):
    async def test_read_goal_waits_for_pending_goal_update(
        self,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        owner = "goal-owner"
        month = date(2026, 3, 1)
        original = AssetGoal(month=month, percent=Decimal(18), all_income=True, category_ids=())
        updated = replace(original, percent=Decimal(19))
        writer = AssetAnalyticsUseCase(
            journal=AssetDatabaseStorage(session=self.db_session),
            storage=FinanceAssetAnalyticsStorage(session=self.db_session),
        )
        await writer.set_goal(SetAssetGoalParams(owner_username=owner, goal=original))
        await self.db_session.commit()
        async with session_maker() as reader_session:
            reader = AssetAnalyticsUseCase(
                journal=AssetDatabaseStorage(session=reader_session),
                storage=FinanceAssetAnalyticsStorage(session=reader_session),
            )
            reader_pid = await reader_session.scalar(select(func.pg_backend_pid()))
            await writer.set_goal(SetAssetGoalParams(owner_username=owner, goal=updated))
            async with asyncio.timeout(10), asyncio.TaskGroup() as reads:
                pending = reads.create_task(
                    reader.goal(AssetGoalParams(owner_username=owner, month=month)),
                )
                # Commit once the read has reached PostgreSQL, independent of task scheduling.
                while not pending.done():
                    if await self.db_session.scalar(select(func.pg_blocking_pids(reader_pid))):
                        break
                await self.db_session.commit()
            assert pending.result() == updated

    async def test_reconciliation_and_selected_income_survive_backdated_payout_and_category_removal(
        self,
    ) -> None:
        owner = "portfolio-owner"
        march = datetime(2026, 3, 1, 12, tzinfo=UTC)
        april = datetime(2026, 4, 1, 12, tzinfo=UTC)
        await self.factory.db.seed_finance_templates(self.db_session)
        finance_db = FinanceDatabaseStorage(session=self.db_session)
        finance = self.factory.core.finance_use_case(finance_db)
        month_command = EnsureFinanceMonthParams(
            owner_username=owner,
            time_zone=ZoneInfo("UTC"),
            language=LanguageEnum.EN,
            now=march,
        )
        month = await finance.ensure_month(month_command)
        income = next(c for c in month.categories if c.kind == FinanceKind.INCOME)
        journal = AssetDatabaseStorage(session=self.db_session)
        analytics = AssetAnalyticsUseCase(
            journal=journal,
            storage=FinanceAssetAnalyticsStorage(session=self.db_session),
        )
        goal = AssetGoal(
            month=march.date(),
            percent=Decimal(10),
            all_income=False,
            category_ids=(income.stable_id,),
        )
        with pytest.raises(FinanceNotFoundError):
            await analytics.set_goal(SetAssetGoalParams(owner_username="outsider", goal=goal))
        await analytics.set_goal(SetAssetGoalParams(owner_username=owner, goal=goal))
        await finance_db.save_rate_set(rate_set=self.factory.core.finance_rate_set(march.date()))
        await finance.create_transaction(
            CreateFinanceTransactionParams(
                period_start=None,
                owner_username=owner,
                now=march,
                actor=FinanceActor.web(owner),
                draft=self.factory.core.finance_transaction_draft(
                    category_id=income.id,
                    amount="100000",
                    currency=FinanceCurrency.RUB,
                    occurred_at=march,
                ),
            ),
        )
        home = await journal.create_location(
            tracker_id=month.tracker_id,
            draft=AssetLocationDraft(name="Home"),
        )
        cash = await journal.create_position(
            tracker_id=month.tracker_id,
            request_id=None,
            signature=None,
            draft=AssetPositionDraft(
                name="Cash",
                location_id=home.id,
                kind=AssetPositionKind.CASH,
                currency=FinanceCurrency.RUB,
                instrument="",
                venue="",
                annual_rate=None,
                matures_on=None,
            ),
        )
        last = date(2026, 3, 31)
        for movement in (
            Factory.movement(Kind.OPENING_EXTERNAL, march.date(), cash.id, amount=10000),
            Factory.movement(Kind.RECONCILE, last, cash.id, amount=12000),
        ):
            await journal.insert_movement(
                tracker_id=month.tracker_id,
                movement=movement,
                posting=None,
            )
        report_command = AssetReportParams(
            owner_username=owner,
            start=march.date(),
            end=last,
            currency=FinanceCurrency.RUB,
            now=april,
        )
        report = await analytics.report(report_command)
        assert report.closing.known_value == 12000
        assert report.reconciliation == 2000
        assert report.net_savings == 0
        assert report.income == 100000
        assert report.target_amount == 10000
        await journal.insert_movement(
            tracker_id=month.tracker_id,
            movement=Factory.movement(Kind.PAYOUT, date(2026, 3, 30), cash.id, amount=2000),
            posting=None,
        )
        following = await finance.ensure_month(replace(month_command, now=april))
        category = next(c for c in following.categories if c.stable_id == income.stable_id)
        await finance.delete_category(
            DeleteFinanceCategoryParams(owner_username=owner, now=april, category_id=category.id),
        )
        new_goal = replace(goal, month=april.date(), percent=Decimal(15))
        assert (
            await analytics.set_goal(SetAssetGoalParams(owner_username=owner, goal=new_goal))
            == new_goal
        )
        with pytest.raises(FinanceNotFoundError):
            await analytics.set_goal(SetAssetGoalParams(owner_username="outsider", goal=new_goal))
        updated = await analytics.report(report_command)
        assert updated.closing.known_value == 12000
        assert updated.reconciliation == 0
        assert updated.payouts == 2000
        assert updated.income == 100000
        assert updated.target_amount == 10000
        empty = await analytics.report(replace(report_command, owner_username="outsider"))
        assert empty.coverage_start is None
        assert empty.coverage_end is None
        assert empty.closing.positions == []
