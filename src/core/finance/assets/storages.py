from abc import ABC, abstractmethod
from datetime import date
from uuid import UUID

from core.finance.assets.schemas import (
    AssetBudgetPosting,
    AssetLocation,
    AssetLocationDraft,
    AssetMovement,
    AssetMovementRevision,
    AssetPosition,
    AssetPositionDraft,
)
from core.finance.schemas import FinanceTransaction


class AssetStorage(ABC):
    @abstractmethod
    async def list_locations(self, *, owner_username: str) -> list[AssetLocation]: ...

    @abstractmethod
    async def list_positions(self, *, owner_username: str) -> list[AssetPosition]: ...

    @abstractmethod
    async def get_location(self, *, owner_username: str, location_id: str) -> AssetLocation: ...

    @abstractmethod
    async def get_position(self, *, owner_username: str, position_id: str) -> AssetPosition: ...

    @abstractmethod
    async def create_location(
        self,
        *,
        tracker_id: str,
        draft: AssetLocationDraft,
    ) -> AssetLocation: ...

    @abstractmethod
    async def update_location(
        self,
        *,
        location_id: str,
        draft: AssetLocationDraft,
    ) -> AssetLocation: ...

    @abstractmethod
    async def create_position(
        self,
        *,
        tracker_id: str,
        draft: AssetPositionDraft,
        request_id: UUID | None,
        signature: str | None,
    ) -> AssetPosition: ...

    @abstractmethod
    async def find_position_request(
        self,
        *,
        tracker_id: str,
        request_id: UUID,
    ) -> tuple[AssetPosition, str | None] | None: ...

    @abstractmethod
    async def archive_position(self, *, position_id: str, archived: bool) -> AssetPosition: ...

    @abstractmethod
    async def delete_unused_position(self, *, tracker_id: str, position_id: str) -> None: ...

    @abstractmethod
    async def update_position(
        self,
        *,
        position_id: str,
        draft: AssetPositionDraft,
    ) -> AssetPosition: ...

    @abstractmethod
    async def list_movements(
        self,
        *,
        owner_username: str,
        end: date | None,
    ) -> list[AssetMovement]: ...

    @abstractmethod
    async def get_movement(self, *, owner_username: str, movement_id: str) -> AssetMovement: ...

    @abstractmethod
    async def revisions(
        self,
        *,
        owner_username: str,
        movement_id: str,
    ) -> list[AssetMovementRevision]: ...

    @abstractmethod
    async def original(self, *, tracker_id: str, request_id: UUID) -> AssetMovement | None: ...

    @abstractmethod
    async def insert_movement(
        self,
        *,
        tracker_id: str,
        movement: AssetMovement,
        posting: AssetBudgetPosting | None,
    ) -> None: ...

    @abstractmethod
    async def revise_movement(
        self,
        *,
        movement: AssetMovement,
        posting: AssetBudgetPosting | None,
    ) -> None: ...

    @abstractmethod
    async def save_payout(
        self,
        *,
        owner_username: str,
        movement: AssetMovement,
        posting: AssetBudgetPosting,
        previous: FinanceTransaction | None,
    ) -> str: ...
