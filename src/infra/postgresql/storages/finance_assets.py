from dataclasses import asdict, dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import delete, insert, or_, select, type_coerce, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from core.finance.assets.schemas import (
    AssetBudgetPosting,
    AssetLocation,
    AssetLocationDraft,
    AssetMovement,
    AssetMovementRevision,
    AssetPosition,
    AssetPositionDraft,
)
from core.finance.assets.storages import AssetStorage
from core.finance.enums import FinanceKind, FinanceRevisionAction, FinanceSource
from core.finance.exceptions import FinanceConflictError, FinanceNotFoundError
from core.finance.schemas import FinanceTransaction
from infra.postgresql.models.finance import (
    FinanceTrackerModel,
    FinanceTransactionModel,
    FinanceTransactionRevisionModel,
)
from infra.postgresql.models.finance_assets import (
    AssetLocationModel,
    AssetMovementModel,
    AssetMovementRevisionModel,
    AssetPositionModel,
)
from infra.postgresql.schemas.finance import FinanceTransactionSnapshotSchema
from infra.postgresql.schemas.finance_assets import AssetDraftSnapshot, AssetRevisionSnapshot


@dataclass(kw_only=True)
class AssetDatabaseStorage(AssetStorage):
    session: AsyncSession

    @staticmethod
    def _position(row: AssetPositionModel) -> AssetPosition:
        return AssetPosition(
            id=row.id,
            archived=row.archived,
            location_id=row.location_id,
            name=row.name,
            kind=row.kind,
            currency=row.currency,
            instrument=row.instrument,
            venue=row.venue,
            annual_rate=row.annual_rate,
            matures_on=row.matures_on,
        )

    @staticmethod
    def _movement(row: AssetMovementModel) -> AssetMovement:
        return AssetMovement(
            id=row.id,
            request_id=row.request_id,
            draft=row.draft.value,
            rate_set_id=row.rate_set_id,
            transaction_id=row.transaction_id,
            source=row.source,
            created_at=row.created_at,
            changed_at=row.changed_at,
            version=row.version,
            deleted=row.deleted,
        )

    async def list_locations(self, *, owner_username: str) -> list[AssetLocation]:
        rows = await self.session.scalars(
            select(AssetLocationModel)
            .join(FinanceTrackerModel)
            .where(FinanceTrackerModel.owner_username == owner_username)
            .order_by(AssetLocationModel.name, AssetLocationModel.id),
        )
        return [AssetLocation(id=row.id, name=row.name) for row in rows]

    async def list_positions(self, *, owner_username: str) -> list[AssetPosition]:
        rows = await self.session.scalars(
            select(AssetPositionModel)
            .join(FinanceTrackerModel)
            .where(FinanceTrackerModel.owner_username == owner_username)
            .order_by(AssetPositionModel.name, AssetPositionModel.id),
        )
        return [self._position(row) for row in rows]

    async def get_location(self, *, owner_username: str, location_id: str) -> AssetLocation:
        row = await self.session.scalar(
            select(AssetLocationModel)
            .join(FinanceTrackerModel)
            .where(
                FinanceTrackerModel.owner_username == owner_username,
                AssetLocationModel.id == location_id,
            ),
        )
        if row is None:
            raise FinanceNotFoundError
        return AssetLocation(id=row.id, name=row.name)

    async def get_position(self, *, owner_username: str, position_id: str) -> AssetPosition:
        row = await self.session.scalar(
            select(AssetPositionModel)
            .join(FinanceTrackerModel)
            .where(
                FinanceTrackerModel.owner_username == owner_username,
                AssetPositionModel.id == position_id,
            ),
        )
        if row is None:
            raise FinanceNotFoundError
        return self._position(row)

    async def create_location(self, *, tracker_id: str, draft: AssetLocationDraft) -> AssetLocation:
        row = AssetLocationModel(tracker_id=tracker_id, name=draft.name)
        self.session.add(row)
        await self.session.flush()
        return AssetLocation(id=row.id, name=row.name)

    async def update_location(
        self,
        *,
        location_id: str,
        draft: AssetLocationDraft,
    ) -> AssetLocation:
        row = (
            await self.session.scalars(
                update(AssetLocationModel)
                .where(AssetLocationModel.id == location_id)
                .values(name=draft.name)
                .returning(AssetLocationModel),
            )
        ).one()
        return AssetLocation(id=row.id, name=row.name)

    async def create_position(
        self,
        *,
        tracker_id: str,
        draft: AssetPositionDraft,
        request_id: UUID | None,
        signature: str | None,
    ) -> AssetPosition:
        row = AssetPositionModel(
            tracker_id=tracker_id,
            creation_request_id=request_id,
            creation_signature=signature,
            **asdict(draft),
        )
        self.session.add(row)
        await self.session.flush()
        return self._position(row)

    async def find_position_request(
        self,
        *,
        tracker_id: str,
        request_id: UUID,
    ) -> tuple[AssetPosition, str | None] | None:
        row = await self.session.scalar(
            select(AssetPositionModel).where(
                AssetPositionModel.tracker_id == tracker_id,
                AssetPositionModel.creation_request_id == request_id,
            ),
        )
        return (self._position(row), row.creation_signature) if row else None

    async def archive_position(self, *, position_id: str, archived: bool) -> AssetPosition:
        row = (
            await self.session.scalars(
                update(AssetPositionModel)
                .where(AssetPositionModel.id == position_id)
                .values(archived=archived)
                .returning(AssetPositionModel),
            )
        ).one()
        return self._position(row)

    async def delete_unused_position(self, *, tracker_id: str, position_id: str) -> None:
        used = (
            select(AssetMovementModel.id)
            .where(
                or_(
                    AssetMovementModel.position_id == position_id,
                    AssetMovementModel.counter_position_id == position_id,
                ),
            )
            .exists()
        )
        snapshot = type_coerce(AssetMovementRevisionModel.snapshot, JSONB)
        in_history = (
            select(AssetMovementRevisionModel.id)
            .join(AssetMovementModel)
            .where(
                AssetMovementModel.tracker_id == tracker_id,
                or_(
                    snapshot[("value", "draft", "position_id")].astext == position_id,
                    snapshot[("value", "draft", "counter_position_id")].astext == position_id,
                ),
            )
            .exists()
        )
        removed = await self.session.scalar(
            delete(AssetPositionModel)
            .where(
                AssetPositionModel.id == position_id,
                ~used,
                ~in_history,
            )
            .returning(AssetPositionModel.id),
        )
        if removed is None:
            raise FinanceConflictError

    async def update_position(
        self,
        *,
        position_id: str,
        draft: AssetPositionDraft,
    ) -> AssetPosition:
        row = (
            await self.session.scalars(
                update(AssetPositionModel)
                .where(AssetPositionModel.id == position_id)
                .values(**asdict(draft))
                .returning(AssetPositionModel),
            )
        ).one()
        return self._position(row)

    async def list_movements(self, *, owner_username: str, end: date | None) -> list[AssetMovement]:
        query = (
            select(AssetMovementModel)
            .join(FinanceTrackerModel)
            .where(FinanceTrackerModel.owner_username == owner_username)
        )
        if end is not None:
            query = query.where(AssetMovementModel.on_date <= end)
        rows = await self.session.scalars(
            query.order_by(
                AssetMovementModel.on_date,
                AssetMovementModel.created_at,
                AssetMovementModel.id,
            ),
        )
        return [self._movement(row) for row in rows]

    async def get_movement(self, *, owner_username: str, movement_id: str) -> AssetMovement:
        row = await self.session.scalar(
            select(AssetMovementModel)
            .join(FinanceTrackerModel)
            .where(
                FinanceTrackerModel.owner_username == owner_username,
                AssetMovementModel.id == movement_id,
            )
            .execution_options(populate_existing=True),
        )
        if row is None:
            raise FinanceNotFoundError
        return self._movement(row)

    async def revisions(
        self,
        *,
        owner_username: str,
        movement_id: str,
    ) -> list[AssetMovementRevision]:
        await self.get_movement(owner_username=owner_username, movement_id=movement_id)
        rows = await self.session.scalars(
            select(AssetMovementRevisionModel.snapshot)
            .where(AssetMovementRevisionModel.movement_id == movement_id)
            .order_by(AssetMovementRevisionModel.version),
        )
        return [row.value for row in rows]

    async def original(self, *, tracker_id: str, request_id: UUID) -> AssetMovement | None:
        snapshot = await self.session.scalar(
            select(AssetMovementRevisionModel.snapshot)
            .join(AssetMovementModel)
            .where(
                AssetMovementModel.tracker_id == tracker_id,
                AssetMovementModel.request_id == request_id,
                AssetMovementRevisionModel.version == 1,
            ),
        )
        return snapshot.value if snapshot else None

    async def insert_movement(
        self,
        *,
        tracker_id: str,
        movement: AssetMovement,
        posting: AssetBudgetPosting | None,
    ) -> None:
        row = AssetMovementModel(
            id=movement.id,
            tracker_id=tracker_id,
            request_id=movement.request_id,
            position_id=movement.draft.position_id,
            counter_position_id=movement.draft.counter_position_id,
            on_date=movement.draft.on_date,
            kind=movement.draft.kind,
            source=movement.source,
            draft=AssetDraftSnapshot(value=movement.draft),
            month_id=posting.month.id if posting else None,
            rate_set_id=movement.rate_set_id,
            budget_amount_rub=posting.amount_rub if posting else None,
            transaction_id=movement.transaction_id,
            version=movement.version,
            deleted=movement.deleted,
            created_at=movement.created_at,
            changed_at=movement.changed_at,
        )
        self.session.add(row)
        await self.session.flush()
        await self._record(movement)

    async def revise_movement(
        self,
        *,
        movement: AssetMovement,
        posting: AssetBudgetPosting | None,
    ) -> None:
        result = await self.session.scalar(
            update(AssetMovementModel)
            .where(
                AssetMovementModel.id == movement.id,
                AssetMovementModel.version == movement.version - 1,
            )
            .values(
                position_id=movement.draft.position_id,
                counter_position_id=movement.draft.counter_position_id,
                on_date=movement.draft.on_date,
                kind=movement.draft.kind,
                source=movement.source,
                draft=AssetDraftSnapshot(value=movement.draft),
                month_id=posting.month.id if posting else None,
                rate_set_id=movement.rate_set_id,
                budget_amount_rub=posting.amount_rub if posting else None,
                transaction_id=movement.transaction_id,
                deleted=movement.deleted,
                version=movement.version,
                changed_at=movement.changed_at,
            )
            .returning(AssetMovementModel.id),
        )
        if result is None:
            raise FinanceConflictError
        await self._record(movement)

    async def _record(self, movement: AssetMovement) -> None:
        self.session.add(
            AssetMovementRevisionModel(
                movement_id=movement.id,
                version=movement.version,
                snapshot=AssetRevisionSnapshot(value=movement),
            ),
        )
        await self.session.flush()

    async def save_payout(
        self,
        *,
        owner_username: str,
        movement: AssetMovement,
        posting: AssetBudgetPosting,
        previous: FinanceTransaction | None,
    ) -> str:
        values = {
            "month_id": posting.month.id,
            "month_category_id": posting.category_id,
            "kind": FinanceKind.INCOME,
            "original_amount": movement.draft.budget_amount,
            "original_currency": posting.currency,
            "amount_rub": posting.amount_rub,
            "rate_set_id": posting.rate_set_id,
            "occurred_at": movement.draft.occurred_at(posting.month.time_zone),
            "description": "",
            "updated_at": movement.changed_at,
            "deleted_at": movement.changed_at if movement.deleted else None,
        }
        if posting.category_id is not None or movement.draft.category_id is None:
            values["former_category_id"] = None
        if previous is None:
            transaction_id: str = (
                await self.session.scalars(
                    insert(FinanceTransactionModel)
                    .values(
                        **values,
                        managed_by_assets=True,
                        author_username=owner_username,
                        author_id=owner_username,
                        source=FinanceSource.WEB,
                        author_label=owner_username,
                        operation_id=movement.id,
                        created_at=movement.changed_at,
                        version=1,
                    )
                    .returning(FinanceTransactionModel.id),
                )
            ).one()
            return transaction_id
        action = FinanceRevisionAction.UPDATE
        if previous.deleted != movement.deleted:
            action = (
                FinanceRevisionAction.DELETE if movement.deleted else FinanceRevisionAction.RESTORE
            )
        self.session.add(
            FinanceTransactionRevisionModel(
                transaction_id=previous.id,
                number=previous.version,
                action=action,
                previous_state=FinanceTransactionSnapshotSchema.from_domain_schema(
                    previous.snapshot(),
                ),
                actor_username=owner_username,
                changed_at=movement.changed_at,
            ),
        )
        result: str | None = await self.session.scalar(
            update(FinanceTransactionModel)
            .where(
                FinanceTransactionModel.id == previous.id,
                FinanceTransactionModel.version == previous.version,
            )
            .values(**values, version=previous.version + 1)
            .returning(FinanceTransactionModel.id),
        )
        if result is None:
            raise FinanceConflictError
        return result
