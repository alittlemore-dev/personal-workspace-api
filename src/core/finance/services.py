from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from core.account_time_zone.clients import AccountTimeZoneReader
from core.finance.enums import (
    FinanceCurrency,
    FinanceEventKind,
    FinanceKind,
    FinanceStatisticsCurrency,
    FinanceStatisticsGranularity,
    FinanceStatisticsPeriod,
)
from core.finance.event_dispatchers import FinanceEventDispatcher
from core.finance.exceptions import FinanceConflictError, FinanceNotFoundError
from core.finance.schemas import (
    Amount,
    FinanceActor,
    FinanceEvent,
    FinanceEventConfig,
    FinanceEventPayload,
    FinanceMonth,
    FinanceStatistics,
    FinanceStatisticsBreakdown,
    FinanceStatisticsCategory,
    FinanceStatisticsComposition,
    FinanceStatisticsFact,
    FinanceStatisticsPoint,
    FinanceStatisticsResult,
    FinanceStatisticsWindow,
    FinanceTracker,
    FinanceTransaction,
    FinanceTransactionMonthParams,
    TelegramFinanceContextParams,
)
from core.finance.storages import FinanceStorage
from core.telegram.exceptions import TelegramAccessError
from core.telegram.schemas import TelegramConnection
from core.telegram.storages import TelegramAccountSettingsReader, TelegramStorage
from core.utils import next_month


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceTelegramAccessService:
    storage: TelegramStorage
    settings_reader: TelegramAccountSettingsReader

    async def resolve(
        self,
        params: TelegramFinanceContextParams,
        *,
        lock: bool,
    ) -> TelegramConnection:
        connection = await self.storage.active_connection_for_participant(
            telegram_user_id=params.telegram_user_id,
            private_chat_id=params.private_chat_id,
            lock=lock,
        )
        if connection is None or not await self.settings_reader.is_enabled(
            owner_username=connection.owner_username,
        ):
            raise TelegramAccessError
        return connection

    async def validate(
        self,
        *,
        actor: FinanceActor,
        owner_username: str,
        now: datetime,
        lock: bool,
    ) -> TelegramConnection:
        if (
            actor.telegram_user_id is None
            or actor.private_chat_id is None
            or not actor.operation_id
        ):
            raise TelegramAccessError
        connection = await self.resolve(
            TelegramFinanceContextParams(
                telegram_user_id=actor.telegram_user_id,
                private_chat_id=actor.private_chat_id,
                now=now,
            ),
            lock=lock,
        )
        connection.require_owner(owner_username=owner_username)
        if (
            connection.id != actor.connection_id
            or str(connection.telegram_user_id) != actor.identifier
        ):
            raise TelegramAccessError
        return connection


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceMonthService:
    storage: FinanceStorage
    time_zone_reader: AccountTimeZoneReader

    async def sync_account_time_zone(
        self,
        *,
        tracker: FinanceTracker,
        owner_username: str,
    ) -> FinanceTracker:
        time_zone = await self.time_zone_reader.get_time_zone(owner_username=owner_username)
        return await self.sync_tracker_time_zone(tracker=tracker, time_zone=time_zone)

    async def sync_tracker_time_zone(
        self,
        *,
        tracker: FinanceTracker,
        time_zone: ZoneInfo,
    ) -> FinanceTracker:
        if tracker.time_zone == time_zone:
            return tracker
        return await self.storage.update_tracker_time_zone(
            tracker=replace(tracker, time_zone=time_zone),
        )

    async def for_transaction(self, params: FinanceTransactionMonthParams) -> FinanceMonth:
        current = await (
            self.storage.lock_month(owner_username=params.owner_username, now=params.now)
            if params.lock
            else self.storage.get_month(owner_username=params.owner_username, now=params.now)
        )
        current.check_transaction_period(params.period_start)
        if params.period_start is None or params.period_start == current.period_start:
            return current
        return await (
            self.storage.lock_month_for_period(
                owner_username=params.owner_username,
                period_start=params.period_start,
            )
            if params.lock
            else self.storage.get_month_for_period(
                owner_username=params.owner_username,
                period_start=params.period_start,
            )
        )

    async def advance(
        self,
        *,
        tracker: FinanceTracker,
        owner_username: str,
        now: datetime,
    ) -> FinanceMonth:
        current_period = tracker.current_period(now)
        month = await self.storage.latest_month(tracker=tracker)
        if month is None:
            raise FinanceNotFoundError
        # A changed account zone can move the current period back across a month boundary.
        # Preserve the saved later month and return the existing local-current month.
        if month.period_start > current_period:
            try:
                return await self.storage.get_month(owner_username=owner_username, now=now)
            except FinanceNotFoundError:
                return await self.storage.create_preceding_month(
                    tracker=tracker,
                    following=month,
                    period_start=current_period,
                    now=now,
                )
        archived = await self.storage.archived_category_ids(tracker=tracker)
        while month.period_start < current_period:
            month = await self.storage.create_rollover_month(
                tracker=tracker,
                rollover=month.rollover(archived),
                now=now,
            )
        if month.period_start != current_period:
            raise FinanceConflictError
        return month


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceEventService:
    dispatcher: FinanceEventDispatcher
    config: FinanceEventConfig

    async def created(
        self,
        *,
        owner_username: str,
        before: FinanceMonth,
        after: FinanceMonth,
        transaction: FinanceTransaction,
        now: datetime,
    ) -> None:
        await self.dispatcher.publish(
            event=FinanceEvent(
                owner_username=owner_username,
                kind=FinanceEventKind.TRANSACTION,
                payload=FinanceEventPayload.for_transaction(after, transaction),
                created_at=now,
                expires_at=now + self.config.lifetime,
            ),
        )
        await self.changed(
            owner_username=owner_username,
            before=before,
            after=after,
            transaction=transaction,
            now=now,
        )

    async def changed(
        self,
        *,
        owner_username: str,
        before: FinanceMonth,
        after: FinanceMonth,
        transaction: FinanceTransaction,
        now: datetime,
    ) -> None:
        for payload in after.crossed_limits(before, transaction):
            await self.dispatcher.publish(
                event=FinanceEvent(
                    owner_username=owner_username,
                    kind=FinanceEventKind.LIMIT,
                    payload=payload,
                    created_at=now,
                    expires_at=now + self.config.lifetime,
                ),
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class FinanceStatisticsService:
    def compose_result(self, composition: FinanceStatisticsComposition) -> FinanceStatisticsResult:
        return FinanceStatisticsResult(
            currency=composition.params.currency,
            reports=[
                self.compose(
                    composition=replace(
                        composition,
                        source=replace(
                            composition.source,
                            facts=[
                                fact
                                for fact in composition.source.facts
                                if fact.currency == currency
                            ],
                        ),
                    ),
                    currency=currency,
                    include_budget=composition.params.currency != FinanceStatisticsCurrency.MONTH
                    or currency == composition.month.currency,
                )
                for currency in composition.source.currencies
            ],
        )

    def compose(
        self,
        *,
        composition: FinanceStatisticsComposition,
        currency: FinanceCurrency,
        include_budget: bool,
    ) -> FinanceStatistics:
        params = composition.params
        month = composition.month
        window = composition.window
        previous_window = composition.previous_window
        source = composition.source
        budget_rate = composition.budget_rate
        monthly = (
            month.statistics_projection(currency, source.facts, budget_rate)
            if include_budget
            and params.period == FinanceStatisticsPeriod.THIS_MONTH
            and (
                currency == month.currency
                or budget_rate is not None
                or not month.needs_budget_rate(FinanceStatisticsCurrency(currency))
            )
            else None
        )
        current_facts = [
            fact
            for fact in source.facts
            if window.contains(fact.occurred_at) and not fact.category_id
        ]
        income = self.breakdown(
            kind=FinanceKind.INCOME,
            currency=currency,
            window=window,
            previous_window=previous_window,
            facts=source.facts,
        )
        expense = self.breakdown(
            kind=FinanceKind.EXPENSE,
            currency=currency,
            window=window,
            previous_window=previous_window,
            facts=source.facts,
        )
        return FinanceStatistics(
            period=params.period,
            currency=currency,
            timezone_name=month.time_zone.key,
            window=window,
            previous_window=previous_window,
            available_since=source.available_since,
            income=income,
            expense=expense,
            net=Amount(income.actual - expense.actual).rounded(currency),
            previous_net=Amount(income.previous - expense.previous).rounded(currency),
            uncategorized_income=Amount(
                sum(
                    (fact.amount for fact in current_facts if fact.kind == FinanceKind.INCOME),
                    Amount(0),
                ),
            ).rounded(currency),
            uncategorized_expense=Amount(
                sum(
                    (fact.amount for fact in current_facts if fact.kind == FinanceKind.EXPENSE),
                    Amount(0),
                ),
            ).rounded(currency),
            monthly=monthly,
            budget_rate_effective_on=budget_rate.effective_on
            if monthly is not None and budget_rate is not None and currency != month.currency
            else None,
        )

    def breakdown(
        self,
        *,
        kind: FinanceKind,
        currency: FinanceCurrency,
        window: FinanceStatisticsWindow,
        previous_window: FinanceStatisticsWindow,
        facts: list[FinanceStatisticsFact],
    ) -> FinanceStatisticsBreakdown:
        current = [
            fact for fact in facts if fact.kind == kind and window.contains(fact.occurred_at)
        ]
        actual = Amount(sum((fact.amount for fact in current), Amount(0))).rounded(currency)
        previous = Amount(
            sum(
                (
                    fact.amount
                    for fact in facts
                    if fact.kind == kind and previous_window.contains(fact.occurred_at)
                ),
                Amount(0),
            ),
        ).rounded(currency)
        by_category: dict[str, Amount] = {}
        names: dict[str, tuple[date, str]] = {}
        for fact in current:
            by_category[fact.category_id] = Amount(
                by_category.get(fact.category_id, Amount(0)) + fact.amount,
            )
            before = names.get(fact.category_id)
            if before is None or fact.category_period >= before[0]:
                names[fact.category_id] = (fact.category_period, fact.category_name)
        categories = [
            FinanceStatisticsCategory(
                id=category_id,
                name=names[category_id][1],
                amount=amount.rounded(currency),
                percentage=(amount / sum(by_category.values()) * 100).quantize(Decimal("0.01")),
            )
            for category_id, amount in sorted(
                by_category.items(),
                key=lambda row: (-row[1], row[0]),
            )
            if amount > 0
        ]
        return FinanceStatisticsBreakdown(
            actual=actual,
            previous=previous,
            change=Amount(actual - previous).rounded(currency),
            change_percent=((actual - previous) / previous * 100).quantize(Decimal("0.01"))
            if previous != 0
            else None,
            timeline=self.timeline(window=window, facts=current, currency=currency),
            categories=categories,
        )

    def timeline(
        self,
        *,
        window: FinanceStatisticsWindow,
        facts: list[FinanceStatisticsFact],
        currency: FinanceCurrency,
    ) -> list[FinanceStatisticsPoint]:
        result: list[FinanceStatisticsPoint] = []
        start = window.start
        while start.astimezone(UTC) < window.end.astimezone(UTC):
            if window.granularity == FinanceStatisticsGranularity.HOUR:
                end = (start.astimezone(UTC) + timedelta(hours=1)).astimezone(window.start.tzinfo)
            elif window.granularity == FinanceStatisticsGranularity.DAY:
                end = start + timedelta(days=1)
            else:
                end = datetime.combine(
                    next_month(start.date().replace(day=1)),
                    datetime.min.time(),
                    window.start.tzinfo,
                )
            end = min(end, window.end)
            amount = Amount(
                sum(
                    (
                        fact.amount
                        for fact in facts
                        if start.astimezone(UTC)
                        <= fact.occurred_at.astimezone(UTC)
                        < end.astimezone(UTC)
                    ),
                    Amount(0),
                ),
            ).rounded(currency)
            result.append(FinanceStatisticsPoint(start=start, end=end, amount=amount))
            start = end
        return result
