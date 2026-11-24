from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Numeric, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from infra.postgresql.models.base import BaseModel


class AssetGoalModel(BaseModel):
    owner_username: Mapped[str] = mapped_column(String(255), primary_key=True)
    month: Mapped[date] = mapped_column(Date, primary_key=True)
    percent: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    all_income: Mapped[bool] = mapped_column(Boolean)
    category_ids: Mapped[list[str]] = mapped_column(ARRAY(String(32)))
