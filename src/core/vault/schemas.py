from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Self


@dataclass(frozen=True, slots=True, kw_only=True)
class VaultEntry:
    id: str
    source: str
    kind: str
    display_name: str
    updated_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class VaultKindStatistics:
    source: str
    kind: str
    total_count: int
    created_last_30_days_count: int
    created_or_updated_last_30_days_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class VaultStatistics:
    total_count: int
    knowledge_count: int
    resume_count: int
    by_kind: list[VaultKindStatistics]
    created_last_30_days_count: int
    created_or_updated_last_30_days_count: int

    @classmethod
    def from_kind_statistics(cls, *, values: list[VaultKindStatistics]) -> Self:
        return cls(
            total_count=sum(value.total_count for value in values),
            knowledge_count=sum(
                value.total_count for value in values if value.source == "knowledge"
            ),
            resume_count=sum(value.total_count for value in values if value.source == "resume"),
            by_kind=values,
            created_last_30_days_count=sum(value.created_last_30_days_count for value in values),
            created_or_updated_last_30_days_count=sum(
                value.created_or_updated_last_30_days_count for value in values
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class VaultConfig:
    recent_limit: int
    activity_period: timedelta


@dataclass(frozen=True, slots=True, kw_only=True)
class GetVaultStatisticsParams:
    author_username: str
    current_datetime: datetime
