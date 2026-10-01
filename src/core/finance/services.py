from dataclasses import dataclass
from datetime import datetime

from core.finance.enums import FinanceEventKind
from core.finance.event_dispatchers import FinanceEventDispatcher
from core.finance.exceptions import FinanceConflictError, FinanceNotFoundError
from core.finance.schemas import (
    FinanceActor,
    FinanceEvent,
    FinanceEventConfig,
    FinanceEventPayload,
    FinanceMonth,
    FinanceTracker,
    FinanceTransaction,
    TelegramFinanceContextParams,
)
from core.finance.storages import FinanceStorage
from core.telegram.exceptions import TelegramAccessError
from core.telegram.schemas import TelegramConnection
from core.telegram.storages import TelegramAccountSettingsReader, TelegramStorage


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

    async def advance(self, *, tracker: FinanceTracker, now: datetime) -> FinanceMonth:
        current_period = tracker.current_period(now)
        month = await self.storage.latest_month(tracker=tracker)
        if month is None:
            raise FinanceNotFoundError
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
