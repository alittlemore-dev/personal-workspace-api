from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from core.finance.enums import FinanceCurrency, FinanceKind, FinanceLimitScope
from infra.postgresql.schemas.finance import FinanceEventPayloadSchema, NotificationPayloadSchema
from infra.postgresql.utils import downgrade, migrate


@pytest.fixture
def before_assets() -> Generator[None]:
    migrate(revision="0011")
    yield
    downgrade(revision="base")


async def test_existing_budget_queue_and_subscriptions_survive_assets_upgrade(
    engine: AsyncEngine,
    before_assets: None,
) -> None:
    _ = before_assets
    old = sa.MetaData()
    now = datetime(2026, 3, 15, tzinfo=UTC)
    async with engine.begin() as conn:
        await conn.run_sync(old.reflect)
        await conn.execute(
            old.tables["finance__finance_tracker_model"]
            .insert()
            .values(
                id="t",
                owner_username="owner",
                timezone_name="UTC",
                created_at=now,
            ),
        )
        await conn.execute(
            old.tables["finance__finance_month_model"]
            .insert()
            .values(
                id="m",
                tracker_id="t",
                period_start=date(2026, 3, 1),
                currency="RUB",
                opening_balance=100,
                version=1,
                created_at=now,
            ),
        )
        payload = FinanceEventPayloadSchema(
            month_id="m",
            period_start=date(2026, 3, 1),
            transaction_id="tx",
            transaction_version=1,
            author_id="owner",
            author_label="Owner",
            source="web",
            kind=FinanceKind.INCOME,
            amount=Decimal(10),
            currency=FinanceCurrency.RUB,
            category_id=None,
            category_name="",
            limit_scope=FinanceLimitScope.CATEGORY,
            planned_amount=None,
            actual_amount=None,
        )
        await conn.execute(
            old.tables["finance_notifications__finance_event_model"]
            .insert()
            .values(
                owner_username="owner",
                kind="TRANSACTION",
                payload=payload.model_dump(mode="json"),
                created_at=now,
                expires_at=now + timedelta(days=1),
            ),
        )
        await conn.execute(
            old.tables["telegram__telegram_connection_model"]
            .insert()
            .values(
                owner_username="owner",
                telegram_user_id=24,
                private_chat_id=24,
                label="mine",
                first_name="Alex",
                username="alex",
                state="ACTIVE",
                requested_at=now,
                connected_at=now,
                state_changed_at=now,
                last_contact_at=now,
                notify_finance_limit=True,
                notify_finance_transaction=True,
            ),
        )
    migrate(revision="0012")
    current = sa.MetaData()
    async with engine.begin() as conn:
        await conn.run_sync(current.reflect)
        assert (
            await conn.scalar(
                sa.select(current.tables["finance__finance_month_model"].c.opening_balance),
            )
            == 100
        )
        assert (
            await conn.scalar(
                sa.select(sa.func.count()).select_from(
                    current.tables["finance_assets__asset_movement_model"],
                ),
            )
            == 0
        )
        saved = (
            (await conn.execute(sa.select(current.tables["telegram__telegram_connection_model"])))
            .mappings()
            .one()
        )
        assert saved["notify_finance_transaction"]
        for name in (
            "notify_asset_movement",
            "notify_savings_goal_reached",
            "notify_assets_month_summary",
            "notify_deposit_maturity",
        ):
            assert saved[name] is False
        event = (
            (
                await conn.execute(
                    sa.select(current.tables["finance_notifications__finance_event_model"]),
                )
            )
            .mappings()
            .one()
        )
        assert event["source_key"] is None
        assert NotificationPayloadSchema.model_validate(event["payload"]).root == payload
    downgrade(revision="0011")
    migrate(revision="0012")
