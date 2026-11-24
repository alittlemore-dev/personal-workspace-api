from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from core.account_time_zone.clients import AccountTimeZoneReader, AccountTimeZoneUnavailableError
from core.finance.assets.analytics_use_cases import AssetAnalyticsUseCase
from core.finance.assets.enums import AssetMovementKind, AssetPositionKind
from core.finance.assets.reports import AssetReport, AssetReportParams
from core.finance.assets.valuation import AssetValuationParams
from core.finance.enums import FinanceCurrency
from core.finance.enums import FinanceEventKind as Kind
from core.finance.schemas import Amount
from core.i18n.enums import LanguageEnum
from core.notifications.finance.schemas import (
    AssetEventSource,
    AssetFinanceDelivery,
    AssetFinanceEvent,
)
from core.utils import next_month

DAY = timedelta(days=1)
MATURITY_NOTICE = timedelta(days=7)
SEND_HOUR = 9


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetSubscriber:
    owner: str
    zone: ZoneInfo


class AssetNoticeStorage(ABC):
    @abstractmethod
    async def subscribers(self, *, owner: str | None, goal: bool) -> list[AssetSubscriber]: ...

    @abstractmethod
    async def currency(self, owner: str, month: date) -> FinanceCurrency | None: ...

    @abstractmethod
    async def record(self, event: AssetFinanceEvent, *, active: bool) -> None: ...

    @abstractmethod
    async def linked_payout(self, owner: str, transaction_id: str) -> bool: ...


@dataclass(kw_only=True)
class AssetNotificationService:
    storage: AssetNoticeStorage
    analytics: AssetAnalyticsUseCase
    public_origin: str
    time_zones: AccountTimeZoneReader

    async def period_report(self, owner: str, month: date, now: datetime) -> AssetReport | None:
        currency = await self.storage.currency(owner, month)
        if currency is None:
            return None
        return await self.analytics.report(
            AssetReportParams(
                owner_username=owner,
                start=month,
                end=next_month(month) - DAY,
                currency=currency,
                now=now,
            ),
        )

    async def publish_movement(
        self,
        owner: str,
        movement_id: str,
        version: int,
        now: datetime,
    ) -> None:
        await self.storage.record(
            AssetFinanceEvent(
                owner_username=owner,
                kind=Kind.ASSET_MOVEMENT,
                source=AssetEventSource(
                    identifier=movement_id,
                    version=version,
                    on_date=now.date(),
                ),
                created_at=now,
                expires_at=now + DAY,
            ),
            active=True,
        )

    @staticmethod
    def reached(report: AssetReport | None) -> bool:
        return bool(
            report
            and report.months
            and report.tracking_start is not None
            and report.tracking_start <= report.start
            and report.income > 0
            and report.target_amount
            and report.target_amount > 0
            and report.net_savings >= report.target_amount,
        )

    async def check_goal(self, owner: str, now: datetime) -> None:
        for subscriber in await self.storage.subscribers(owner=owner, goal=True):
            month = now.astimezone(subscriber.zone).date().replace(day=1)
            report = await self.period_report(owner, month, now)
            await self.storage.record(
                AssetFinanceEvent(
                    owner_username=owner,
                    kind=Kind.SAVINGS_GOAL,
                    source=AssetEventSource(identifier=month.isoformat(), version=1, on_date=month),
                    created_at=now,
                    expires_at=now + DAY,
                ),
                active=self.reached(report),
            )

    async def plan_calendar(self, now: datetime) -> None:
        for subscriber in await self.storage.subscribers(owner=None, goal=False):
            try:
                zone = await self.time_zones.get_time_zone(owner_username=subscriber.owner)
            except AccountTimeZoneUnavailableError:
                continue
            local = now.astimezone(zone)
            if local.hour < SEND_HOUR:
                continue
            today = local.date()
            expires = datetime.combine(today + DAY, time.min, tzinfo=zone)
            if today.day == 1:
                month = (today - DAY).replace(day=1)
                report = await self.period_report(subscriber.owner, month, now)
                if report and report.months:
                    await self.storage.record(
                        AssetFinanceEvent(
                            owner_username=subscriber.owner,
                            kind=Kind.MONTH_SUMMARY,
                            source=AssetEventSource(
                                identifier=month.isoformat(),
                                version=1,
                                on_date=month,
                            ),
                            created_at=now,
                            expires_at=expires,
                        ),
                        active=True,
                    )
            for position in await self.analytics.journal.list_positions(
                owner_username=subscriber.owner,
            ):
                if (
                    position.kind == AssetPositionKind.DEPOSIT
                    and position.matures_on == today + MATURITY_NOTICE
                ):
                    await self.storage.record(
                        AssetFinanceEvent(
                            owner_username=subscriber.owner,
                            kind=Kind.DEPOSIT_MATURITY,
                            source=AssetEventSource(
                                identifier=position.id,
                                version=1,
                                on_date=position.matures_on,
                            ),
                            created_at=now,
                            expires_at=expires,
                        ),
                        active=True,
                    )

    async def message(self, delivery: AssetFinanceDelivery, now: datetime) -> str | None:
        connection = delivery.connection
        if not delivery.subscribed or connection is None:
            return None
        event = delivery.event
        owner = event.owner_username
        ru = connection.language == LanguageEnum.RU
        if event.kind == Kind.ASSET_MOVEMENT:
            return await self.movement_message(event, ru=ru)
        zone = await self.time_zones.get_time_zone(owner_username=owner)
        local = now.astimezone(zone)
        if event.kind == Kind.DEPOSIT_MATURITY:
            return await self.deposit_message(event, local, ru=ru)
        return await self.month_message(event, local, ru=ru)

    async def month_message(
        self,
        event: AssetFinanceEvent,
        local: datetime,
        *,
        ru: bool,
    ) -> str | None:
        day = event.source.on_date
        if event.kind == Kind.MONTH_SUMMARY and (
            local.hour < SEND_HOUR or local.date() != next_month(day)
        ):
            return None
        report = await self.period_report(event.owner_username, day, local)
        if (
            report is None
            or not report.months
            or (
                event.kind == Kind.SAVINGS_GOAL
                and (local.date().replace(day=1) != day or not self.reached(report))
            )
        ):
            return None
        return self.with_link(
            self.report_text(report, goal=event.kind == Kind.SAVINGS_GOAL, ru=ru),
            day,
            tab="assets",
            position_id=None,
        )

    def with_link(self, text: str, day: date, *, tab: str, position_id: str | None) -> str:
        url = f"{self.public_origin}/personal-workspace/finance"
        position = f"&assetPosition={position_id}" if position_id else ""
        return f"{text}\n{url}?tab={tab}&year={day.year}&month={day.month}{position}"

    @staticmethod
    def date_label(day: date, *, ru: bool) -> str:
        return day.strftime("%d.%m.%Y" if ru else "%m/%d/%Y")

    async def movement_message(self, event: AssetFinanceEvent, *, ru: bool) -> str | None:
        source = event.source
        owner = event.owner_username
        movement = await self.analytics.journal.get_movement(
            owner_username=owner,
            movement_id=source.identifier,
        )
        if movement.deleted or movement.version != source.version or not movement.draft.notifies:
            return None
        day = movement.draft.on_date
        position = await self.analytics.journal.get_position(
            owner_username=owner,
            position_id=movement.draft.position_id,
        )
        names = {
            AssetMovementKind.BUY: ("Покупка бумаг", "Securities purchase"),
            AssetMovementKind.SELL: ("Продажа бумаг", "Securities sale"),
            AssetMovementKind.DEPOSIT_EXTERNAL: ("Пополнение", "Deposit"),
            AssetMovementKind.WITHDRAW_EXTERNAL: ("Снятие", "Withdrawal"),
            AssetMovementKind.CONTRIBUTION: ("Взнос", "Contribution"),
            AssetMovementKind.BUY_FROM_BUDGET: (
                "Взнос на покупку",
                "Contribution for purchase",
            ),
            AssetMovementKind.WITHDRAWAL: ("Возврат в бюджет", "Withdrawal to budget"),
            AssetMovementKind.PAYOUT: ("Выплата", "Payout"),
            AssetMovementKind.PAYOUT_TO_BUDGET: ("Выплата в бюджет", "Payout to budget"),
        }
        label = names[movement.draft.kind][0 if ru else 1]
        value = Amount(movement.draft.budget_amount).rounded(position.currency)
        label_date = self.date_label(day, ru=ru)
        text = f"{label} · {label_date}\n{position.name} · {value} {position.currency}"
        if movement.draft.entered_currency not in (None, position.currency):
            text += f" ({movement.draft.entered_amount} {movement.draft.entered_currency})"
        return self.with_link(text, day, tab="transactions", position_id=position.id)

    async def deposit_message(
        self,
        event: AssetFinanceEvent,
        local: datetime,
        *,
        ru: bool,
    ) -> str | None:
        source = event.source
        day = source.on_date
        owner = event.owner_username
        if local.hour < SEND_HOUR or local.date() + MATURITY_NOTICE != day:
            return None
        position = await self.analytics.journal.get_position(
            owner_username=owner,
            position_id=source.identifier,
        )
        if position.kind != AssetPositionKind.DEPOSIT or position.matures_on != day:
            return None
        valuation = await self.analytics.positions(
            AssetValuationParams(
                owner_username=owner,
                as_of=local.date(),
                currency=position.currency,
            ),
        )
        if not any(
            p.id == position.id and p.quantity is not None and p.quantity > 0
            for p in valuation.positions
        ):
            return None
        label = "Окончание вклада" if ru else "Deposit maturity"
        text = f"{label} · {self.date_label(day, ru=ru)}\n{position.name}"
        return self.with_link(text, local.date(), tab="overview", position_id=None)

    @staticmethod
    def report_text(report: AssetReport, *, goal: bool, ru: bool) -> str:
        month = report.months[-1]
        heading = (
            ("Цель достигнута" if ru else "Savings goal reached")
            if goal
            else ("Активы за месяц" if ru else "Monthly assets")
        )
        period = month.month.strftime("%m.%Y" if ru else "%m/%Y")
        lines = [f"{heading} · {period}"]
        money: list[tuple[str, Decimal | None]] = []
        if not goal:
            capital = (
                ("Капитал" if ru else "Capital")
                if report.closing.complete
                else ("Оценённая часть" if ru else "Known capital")
            )
            money.extend(
                [
                    (capital, report.closing.known_value),
                    ("Взносы" if ru else "Contributions", report.deposits),
                    ("Возвраты" if ru else "Withdrawals", report.withdrawals),
                ],
            )
        money.extend(
            [
                ("Накопления" if ru else "Net savings", report.net_savings),
                ("Цель" if ru else "Target", report.target_amount),
            ],
        )
        if report.target_amount is not None:
            money.append(
                ("Разница" if ru else "Difference", report.net_savings - report.target_amount),
            )
        lines.extend(
            f"{key} · {value} {report.currency}" for key, value in money if value is not None
        )
        shares = [
            ("Норма" if ru else "Savings rate", report.actual_percent),
            ("Цель" if ru else "Target rate", month.target_percent),
        ]
        if not goal:
            shares.append(
                ("Без процентов" if ru else "Non-interest-bearing", report.non_interest_percent),
            )
            if report.coverage_start and report.coverage_end:
                lines.append(f"{report.coverage_start} / {report.coverage_end}")
        lines.extend(f"{label} · {share:.2f}%" for label, share in shares if share is not None)
        return "\n".join(lines)
