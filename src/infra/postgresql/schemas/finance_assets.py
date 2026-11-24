from pydantic import BaseModel, ConfigDict

from core.finance.assets.schemas import AssetMovement, AssetMovementDraft


class AssetDraftSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    value: AssetMovementDraft


class AssetRevisionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    value: AssetMovement
