from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from core.finance.assets.enums import AssetMovementKind as Kind
from core.finance.assets.schemas import (
    AssetBudgetPosting,
    AssetLocation,
    AssetLocationDraft,
    AssetMovement,
    AssetMovementCommand,
    AssetMovementDeletion,
    AssetMovementDraft,
    AssetMovementUpdate,
    AssetOpeningPreviewParams,
    AssetPosition,
    AssetPositionDraft,
    AssetWriteContext,
    CreateOverviewAsset,
)
from core.finance.assets.storages import AssetStorage
from core.finance.assets.valuation import AssetLedger
from core.finance.clients import FinanceRateClient
from core.finance.enums import FinanceCurrency, FinanceKind
from core.finance.exceptions import (
    FinanceConflictError,
    FinanceNotFoundError,
    FinanceRateUnavailableError,
    InvalidFinanceDataError,
)
from core.finance.schemas import (
    Amount,
    FinanceMonth,
    FinanceOpeningProjection,
    FinanceRateSet,
    FinanceTracker,
    FinanceTransaction,
    FinanceTransactionDeletionChange,
    FinanceTransactionMonthParams,
    SetFinanceTransactionDeletedParams,
)
from core.finance.services import FinanceEventService, FinanceMonthService
from core.finance.storages import FinanceStorage


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetMovementService:
    storage: AssetStorage
    finance: FinanceStorage
    months: FinanceMonthService
    rate_client: FinanceRateClient
    events: FinanceEventService

    async def _tracker(self, owner_username: str) -> FinanceTracker:
        tracker = await self.finance.lock_tracker(owner_username=owner_username)
        if tracker is None:
            raise FinanceNotFoundError
        return tracker

    async def create_location(
        self,
        *,
        owner_username: str,
        draft: AssetLocationDraft,
    ) -> AssetLocation:
        tracker = await self._tracker(owner_username)
        draft.validate()
        return await self.storage.create_location(tracker_id=tracker.id, draft=draft)

    async def update_location(
        self,
        *,
        owner_username: str,
        location_id: str,
        draft: AssetLocationDraft,
    ) -> AssetLocation:
        await self._tracker(owner_username)
        await self.storage.get_location(owner_username=owner_username, location_id=location_id)
        draft.validate()
        return await self.storage.update_location(location_id=location_id, draft=draft)

    async def create_position(
        self,
        *,
        owner_username: str,
        draft: AssetPositionDraft,
    ) -> AssetPosition:
        tracker = await self._tracker(owner_username)
        await self.storage.get_location(
            owner_username=owner_username,
            location_id=draft.location_id,
        )
        draft.validate()
        return await self.storage.create_position(
            tracker_id=tracker.id,
            draft=draft,
            request_id=None,
            signature=None,
        )

    async def create_overview_asset(self, command: CreateOverviewAsset) -> AssetPosition:
        tracker = await self._tracker(command.owner_username)
        signature = command.signature()
        previous = await self.storage.find_position_request(
            tracker_id=tracker.id,
            request_id=command.request_id,
        )
        if previous is not None:
            position, original_signature = previous
            if original_signature != signature:
                raise FinanceConflictError
            return position
        draft = command.position
        draft.validate()
        if command.on_date > command.now.astimezone(tracker.time_zone).date():
            raise InvalidFinanceDataError
        if draft.location_id:
            await self.storage.get_location(
                owner_username=command.owner_username,
                location_id=draft.location_id,
            )
        else:
            name = command.default_location_name.strip()
            locations = await self.storage.list_locations(owner_username=command.owner_username)
            location = next((item for item in locations if item.name == name), None)
            if location is None:
                new_location = AssetLocationDraft(name=name)
                new_location.validate()
                location = await self.storage.create_location(
                    tracker_id=tracker.id,
                    draft=new_location,
                )
            draft = replace(draft, location_id=location.id)
        position = await self.storage.create_position(
            tracker_id=tracker.id,
            draft=draft,
            request_id=command.request_id,
            signature=signature,
        )
        if command.amount is not None:
            await self.apply(
                AssetMovementCommand(
                    owner_username=command.owner_username,
                    source=command.source,
                    can_write_budget=False,
                    now=command.now,
                    request_id=command.request_id,
                    draft=AssetMovementDraft(
                        kind=Kind.VALUATION if draft.kind.security else Kind.OPENING_EXTERNAL,
                        on_date=command.on_date,
                        position_id=position.id,
                        counter_position_id=None,
                        amount=None if draft.kind.security else command.amount,
                        total_value=command.amount if draft.kind.security else None,
                        counter_amount=None,
                        quantity=None,
                        category_id=None,
                        note="",
                    ),
                ),
            )
        return position

    async def archive_position(
        self,
        *,
        owner_username: str,
        position_id: str,
        archived: bool,
    ) -> AssetPosition:
        await self._tracker(owner_username)
        await self.storage.get_position(owner_username=owner_username, position_id=position_id)
        return await self.storage.archive_position(position_id=position_id, archived=archived)

    async def delete_position(self, *, owner_username: str, position_id: str) -> None:
        tracker = await self._tracker(owner_username)
        await self.storage.get_position(owner_username=owner_username, position_id=position_id)
        await self.storage.delete_unused_position(tracker_id=tracker.id, position_id=position_id)

    async def update_position(
        self,
        *,
        owner_username: str,
        position_id: str,
        draft: AssetPositionDraft,
    ) -> AssetPosition:
        await self._tracker(owner_username)
        current = await self.storage.get_position(
            owner_username=owner_username,
            position_id=position_id,
        )
        if current.archived:
            raise FinanceConflictError
        await self.storage.get_location(
            owner_username=owner_username,
            location_id=draft.location_id,
        )
        current.check_identity(draft)
        draft.validate()
        return await self.storage.update_position(position_id=position_id, draft=draft)

    async def _month(self, context: AssetWriteContext, day: date) -> FinanceMonth:
        return await self.months.for_transaction(
            FinanceTransactionMonthParams(
                owner_username=context.owner_username,
                now=context.now,
                period_start=day.replace(day=1),
                lock=True,
            ),
        )

    async def _rate(
        self,
        day: date,
        existing: AssetMovement | None,
    ) -> tuple[str | None, FinanceRateSet]:
        if existing and existing.draft.on_date == day and existing.rate_set_id:
            return existing.rate_set_id, await self.finance.get_rate_set(
                rate_set_id=existing.rate_set_id,
            )
        cached = await self.finance.rate_for_date(on_date=day)
        if cached:
            return cached
        try:
            return None, await self.rate_client.fetch(on_date=day)
        except FinanceRateUnavailableError:
            latest = await self.finance.latest_rate_before_date(on_date=day)
            if latest is None:
                raise
            return latest

    async def preview_opening(
        self,
        params: AssetOpeningPreviewParams,
    ) -> tuple[Amount, FinanceCurrency]:
        tracker = await self._tracker(params.owner_username)
        if params.on_date > params.now.astimezone(tracker.time_zone).date():
            raise InvalidFinanceDataError
        position = await self.storage.get_position(
            owner_username=params.owner_username,
            position_id=params.position_id,
        )
        position.currency.validate_money(Amount(params.amount), positive=False)
        existing = (
            await self.storage.get_movement(
                owner_username=params.owner_username,
                movement_id=params.movement_id,
            )
            if params.movement_id is not None
            else None
        )
        if existing and existing.deleted:
            raise FinanceConflictError
        month = await self.months.for_transaction(
            FinanceTransactionMonthParams(
                owner_username=params.owner_username,
                now=params.now,
                period_start=params.on_date.replace(day=1),
                lock=False,
            ),
        )
        amount_rub, month_rate = Amount(0), Decimal(1)
        if params.amount:
            _, rates = await self._rate(params.on_date, existing)
            amount_rub = Amount(params.amount * rates.rates[position.currency])
            amount_rub.validate_range()
            month_rate = rates.rates[month.currency]
        projected = await self.finance.project_opening_balance(
            month=month,
            projection=FinanceOpeningProjection(
                currency=month.currency,
                amount_rub=amount_rub,
                month_rate=month_rate,
                movement_id=params.movement_id,
                transaction_id=existing.transaction_id if existing else None,
            ),
        )
        return projected, month.currency

    async def _prepare_movement(
        self,
        context: AssetWriteContext,
        movement: AssetMovement,
        tracker: FinanceTracker,
        existing: AssetMovement | None,
    ) -> tuple[AssetMovement, AssetBudgetPosting | None]:
        draft = movement.draft
        context.check_permission(draft.kind)
        if draft.on_date > context.now.astimezone(tracker.time_zone).date():
            raise InvalidFinanceDataError
        primary = await self.storage.get_position(
            owner_username=context.owner_username,
            position_id=draft.position_id,
        )
        counter = (
            await self.storage.get_position(
                owner_username=context.owner_username,
                position_id=draft.counter_position_id,
            )
            if draft.counter_position_id is not None
            else None
        )
        previous_ids = (
            {existing.draft.position_id, existing.draft.counter_position_id} if existing else set()
        )
        if any(p.archived and p.id not in previous_ids for p in (primary, counter) if p):
            raise FinanceConflictError
        draft.validate(primary, counter)
        if draft.kind.affects_budget:
            posting = await self._budget_posting(context, draft, primary, existing)
            return replace(movement, rate_set_id=posting.rate_set_id), posting
        if draft.external_funds or draft.kind in {Kind.DEPOSIT_EXTERNAL, Kind.WITHDRAW_EXTERNAL}:
            rate_id, rate = await self._saved_rate(draft.on_date, existing)
            movement = replace(
                movement,
                rate_set_id=rate_id,
                draft=draft.in_position_currency(primary.currency, rate),
            )
        return movement, None

    async def _saved_rate(
        self,
        day: date,
        existing: AssetMovement | None,
    ) -> tuple[str, FinanceRateSet]:
        rate_id, rate = await self._rate(day, existing)
        if rate_id is None:
            rate_id = await self.finance.save_rate_set(rate_set=rate)
            rate = await self.finance.get_rate_set(rate_set_id=rate_id)
        return rate_id, rate

    async def _budget_posting(
        self,
        context: AssetWriteContext,
        draft: AssetMovementDraft,
        primary: AssetPosition,
        existing: AssetMovement | None,
    ) -> AssetBudgetPosting:
        month = await self._month(context, draft.on_date)
        category_id = draft.category_id
        if category_id is not None:
            try:
                category = month.get_category(category_id)
            except FinanceNotFoundError:
                if (
                    existing is None
                    or existing.draft.category_id != category_id
                    or (existing.draft.on_date.replace(day=1) != month.period_start)
                ):
                    raise
                category_id = None
            else:
                if category.kind != FinanceKind.INCOME:
                    raise InvalidFinanceDataError
                category.check_accepting_transaction(
                    existing.draft.category_id if existing else None,
                )
        rate_id, rate = await self._saved_rate(draft.on_date, existing)
        amount_rub = Amount(draft.budget_amount * rate.rates[primary.currency])
        amount_rub.validate_range()
        return AssetBudgetPosting(
            category_id=category_id,
            month=month,
            rate_set_id=rate_id,
            amount_rub=amount_rub,
            currency=primary.currency,
        )

    async def _transaction(
        self,
        context: AssetWriteContext,
        existing: AssetMovement,
    ) -> FinanceTransaction | None:
        if existing.transaction_id is None:
            return None
        return await self.finance.transaction_for_period(
            owner_username=context.owner_username,
            period_start=existing.draft.on_date.replace(day=1),
            transaction_id=existing.transaction_id,
        )

    async def _remove_payout(
        self,
        context: AssetWriteContext,
        existing: AssetMovement,
        transaction: FinanceTransaction,
    ) -> None:
        month = await self._month(context, existing.draft.on_date)
        await self.finance.set_transaction_deleted(
            write=FinanceTransactionDeletionChange(
                transaction=transaction,
                month=month,
                params=SetFinanceTransactionDeletedParams(
                    owner_username=context.owner_username,
                    now=context.now,
                    period_start=month.period_start,
                    transaction_id=transaction.id,
                    version=transaction.version,
                    deleted=True,
                ),
            ),
        )

    async def _save_link(
        self,
        context: AssetWriteContext,
        movement: AssetMovement,
        posting: AssetBudgetPosting | None,
        existing: AssetMovement | None,
    ) -> AssetMovement:
        previous = await self._transaction(context, existing) if existing else None
        if movement.draft.kind == Kind.PAYOUT_TO_BUDGET and posting is not None:
            transaction_id = await self.storage.save_payout(
                owner_username=context.owner_username,
                movement=movement,
                posting=posting,
                previous=previous,
            )
            return replace(movement, transaction_id=transaction_id)
        if previous and existing:
            await self._remove_payout(context, existing, previous)
        return replace(movement, transaction_id=None)

    async def _check_budget_period(
        self,
        context: AssetWriteContext,
        existing: AssetMovement,
    ) -> None:
        if existing.draft.kind.affects_budget:
            await self._month(context, existing.draft.on_date)

    async def apply(self, command: AssetMovementCommand) -> AssetMovement:
        tracker = await self._tracker(command.owner_username)
        command.check_permission(command.draft.kind)
        original = await self.storage.original(tracker_id=tracker.id, request_id=command.request_id)
        if original:
            if not original.draft.matches_request(command.draft):
                raise FinanceConflictError
            return original
        movement, posting = await self._prepare_movement(
            command,
            AssetMovement.create(command),
            tracker,
            None,
        )
        await self._check_history(command, movement)
        movement = await self._save_link(command, movement, posting, None)
        await self.storage.insert_movement(
            tracker_id=tracker.id,
            movement=movement,
            posting=posting,
        )
        if movement.draft.notifies:
            await self.events.dispatcher.publish_asset_movement(
                owner_username=command.owner_username,
                movement_id=movement.id,
                version=movement.version,
                now=command.now,
            )
        if movement.transaction_id and posting:
            result = await self.finance.transaction_for_period(
                owner_username=command.owner_username,
                period_start=posting.month.period_start,
                transaction_id=movement.transaction_id,
            )
            await self.events.created(
                owner_username=command.owner_username,
                before=posting.month,
                after=await self._month(command, movement.draft.on_date),
                transaction=result,
                now=command.now,
            )
        else:
            await self.events.dispatcher.check_asset_goal(
                owner_username=command.owner_username,
                now=command.now,
            )
        return movement

    async def _check_history(
        self,
        context: AssetWriteContext,
        movement: AssetMovement,
    ) -> None:
        history = await self.storage.list_movements(owner_username=context.owner_username, end=None)
        history = [m for m in history if m.id != movement.id and not m.deleted]
        if not movement.deleted:
            self._check_observations(movement.draft, [m.draft for m in history])
            history.append(movement)
        positions = await self.storage.list_positions(owner_username=context.owner_username)
        AssetLedger.validate_balances(positions, history, edited_id=movement.id)

    @staticmethod
    def _check_observations(draft: AssetMovementDraft, other: list[AssetMovementDraft]) -> None:
        statements = [m.on_date for m in other if m.kind == Kind.STATEMENT]
        regular = [m.on_date for m in other if m.kind != Kind.STATEMENT]
        if draft.kind == Kind.STATEMENT:
            if regular and draft.on_date >= min(regular):
                raise FinanceConflictError
        elif statements and draft.on_date <= max(statements):
            raise FinanceConflictError
        if draft.kind in {Kind.RECONCILE, Kind.STATEMENT, Kind.VALUATION} and any(
            m.kind == draft.kind
            and m.on_date == draft.on_date
            and m.position_id == draft.position_id
            for m in other
        ):
            raise FinanceConflictError
        opening = {Kind.OPENING_EXTERNAL, Kind.OPENING_BUDGET}
        if draft.kind in opening and any(
            m.kind in opening and m.position_id == draft.position_id for m in other
        ):
            raise FinanceConflictError

    async def update_movement(self, command: AssetMovementUpdate) -> AssetMovement:
        tracker = await self._tracker(command.owner_username)
        current = await self.storage.get_movement(
            owner_username=command.owner_username,
            movement_id=command.movement_id,
        )
        current.check_change(command, tracker)
        command.check_permission(command.draft.kind)
        if current.deleted:
            raise FinanceConflictError
        await self._check_budget_period(command, current)
        movement = replace(
            current,
            draft=command.draft,
            version=current.version + 1,
            changed_at=command.now,
            source=command.source,
            rate_set_id=None,
        )
        movement, posting = await self._prepare_movement(command, movement, tracker, current)
        await self._check_history(command, movement)
        movement = await self._save_link(command, movement, posting, current)
        await self.storage.revise_movement(movement=movement, posting=posting)
        await self.events.dispatcher.check_asset_goal(
            owner_username=command.owner_username,
            now=command.now,
        )
        return movement

    async def set_deleted(self, command: AssetMovementDeletion) -> AssetMovement:
        tracker = await self._tracker(command.owner_username)
        current = await self.storage.get_movement(
            owner_username=command.owner_username,
            movement_id=command.movement_id,
        )
        current.check_change(command, tracker)
        if current.deleted == command.deleted:
            raise FinanceConflictError
        movement = replace(
            current,
            deleted=command.deleted,
            version=current.version + 1,
            changed_at=command.now,
            source=command.source,
        )
        movement, posting = await self._prepare_movement(command, movement, tracker, current)
        await self._check_history(command, movement)
        movement = await self._save_link(command, movement, posting, current)
        await self.storage.revise_movement(movement=movement, posting=posting)
        await self.events.dispatcher.check_asset_goal(
            owner_username=command.owner_username,
            now=command.now,
        )
        return movement
