from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

from core.finance.assets.goals import AssetGoal, AssetGoalParams, SetAssetGoalParams
from core.finance.assets.reports import (
    AssetReport,
    AssetReportCalculator,
    AssetReportFacts,
    AssetReportParams,
)
from core.finance.assets.schemas import (
    AssetLocation,
    AssetMovement,
    AssetMovementRevision,
    AssetMovementsParams,
    AssetRevisionsParams,
)
from core.finance.assets.storages import AssetStorage
from core.finance.assets.valuation import (
    AssetLedger,
    AssetRates,
    AssetValuation,
    AssetValuationParams,
)
from core.finance.exceptions import FinanceNotFoundError, InvalidFinanceDataError


class AssetAnalyticsStorage(ABC):
    @abstractmethod
    async def lock_owner(self, *, owner_username: str, writing: bool) -> None: ...

    @abstractmethod
    async def rates(self, *, end: date) -> AssetRates: ...

    @abstractmethod
    async def facts(self, params: AssetReportParams) -> AssetReportFacts: ...

    @abstractmethod
    async def goal(self, params: AssetGoalParams) -> AssetGoal | None: ...

    @abstractmethod
    async def income_categories(self, *, owner_username: str, ids: tuple[str, ...]) -> set[str]: ...

    @abstractmethod
    async def set_goal(self, params: SetAssetGoalParams) -> None: ...


@dataclass(kw_only=True)
class AssetAnalyticsUseCase:
    storage: AssetAnalyticsStorage
    journal: AssetStorage

    async def locations(self, *, owner_username: str) -> list[AssetLocation]:
        await self.storage.lock_owner(owner_username=owner_username, writing=False)
        return await self.journal.list_locations(owner_username=owner_username)

    async def movements(self, params: AssetMovementsParams) -> list[AssetMovement]:
        if params.start and params.end and params.start > params.end:
            raise InvalidFinanceDataError
        await self.storage.lock_owner(owner_username=params.owner_username, writing=False)
        rows = await self.journal.list_movements(
            owner_username=params.owner_username,
            end=params.end,
        )
        return [row for row in rows if params.start is None or row.draft.on_date >= params.start]

    async def revisions(self, params: AssetRevisionsParams) -> list[AssetMovementRevision]:
        await self.storage.lock_owner(owner_username=params.owner_username, writing=False)
        return await self.journal.revisions(
            owner_username=params.owner_username,
            movement_id=params.movement_id,
        )

    async def positions(self, params: AssetValuationParams) -> AssetValuation:
        await self.storage.lock_owner(owner_username=params.owner_username, writing=False)
        ledger = AssetLedger(
            positions=await self.journal.list_positions(owner_username=params.owner_username),
            movements=await self.journal.list_movements(
                owner_username=params.owner_username,
                end=params.as_of,
            ),
            rates=await self.storage.rates(end=params.as_of),
        )
        return ledger.evaluate(params.as_of, params.currency)

    async def report(self, params: AssetReportParams) -> AssetReport:
        await self.storage.lock_owner(owner_username=params.owner_username, writing=False)
        facts = await self.storage.facts(params)
        today = params.now.astimezone(facts.zone).date()
        end = min(today, params.end)
        ledger = AssetLedger(
            positions=await self.journal.list_positions(owner_username=params.owner_username),
            movements=await self.journal.list_movements(
                owner_username=params.owner_username,
                end=end,
            ),
            rates=await self.storage.rates(end=end),
        )
        return AssetReportCalculator(
            ledger=ledger,
            facts=facts,
            currency=params.currency,
            today=today,
        ).build(params.start, params.end)

    async def goal(self, params: AssetGoalParams) -> AssetGoal | None:
        await self.storage.lock_owner(owner_username=params.owner_username, writing=False)
        return await self.storage.goal(params)

    async def set_goal(self, params: SetAssetGoalParams) -> AssetGoal:
        await self.storage.lock_owner(owner_username=params.owner_username, writing=True)
        if params.goal.category_ids:
            owned = await self.storage.income_categories(
                owner_username=params.owner_username,
                ids=params.goal.category_ids,
            )
            if missing := set(params.goal.category_ids) - owned:
                previous = await self.storage.goal(
                    AssetGoalParams(owner_username=params.owner_username, month=params.goal.month),
                )
                if previous is None or not missing.issubset(previous.category_ids):
                    raise FinanceNotFoundError
        await self.storage.set_goal(params)
        return params.goal
