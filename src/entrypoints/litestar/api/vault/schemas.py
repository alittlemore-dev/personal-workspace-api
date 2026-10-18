from pydantic import Field

from core.vault.schemas import VaultEntry, VaultKindStatistics, VaultStatistics
from entrypoints.litestar.api.schemas import CamelCaseSchema


class VaultEntryResponseSchema(CamelCaseSchema):
    id: str = Field(
        description="Opaque resource identifier; use the value returned by this API.",
        examples=["4e92d4de561f4bc7a3eed227868952db"],
    )
    source: str = Field(description="Source domain of this item.", examples=["knowledge"])
    kind: str = Field(description="Item kind within its source domain.", examples=["person"])
    display_name: str = Field(description="Human-readable display name.", examples=["Alex Morgan"])
    updated_at: str = Field(
        description="Last modification timestamp in ISO 8601 format.",
        examples=["2026-10-18T10:30:00Z"],
    )

    @classmethod
    def from_domain_schema(cls, *, schema: VaultEntry) -> VaultEntryResponseSchema:
        return cls.model_construct(
            id=schema.id,
            source=schema.source,
            kind=schema.kind,
            display_name=schema.display_name,
            updated_at=schema.updated_at.isoformat(),
        )


class VaultRecentResponseSchema(CamelCaseSchema):
    items: list[VaultEntryResponseSchema] = Field(description="Items returned by this operation.")

    @classmethod
    def from_domain_schema(cls, *, items: list[VaultEntry]) -> VaultRecentResponseSchema:
        return cls.model_construct(
            items=[VaultEntryResponseSchema.from_domain_schema(schema=item) for item in items],
        )


class VaultKindStatisticsResponseSchema(CamelCaseSchema):
    source: str = Field(description="Source domain of this item.", examples=["knowledge"])
    kind: str = Field(description="Item kind within its source domain.", examples=["person"])
    total_count: int = Field(
        description="Total number of matching records before pagination.",
        examples=[42],
    )

    @classmethod
    def from_domain_schema(
        cls,
        *,
        schema: VaultKindStatistics,
    ) -> VaultKindStatisticsResponseSchema:
        return cls.model_construct(
            source=schema.source,
            kind=schema.kind,
            total_count=schema.total_count,
        )


class VaultStatisticsResponseSchema(CamelCaseSchema):
    total_count: int = Field(
        description="Total number of matching records before pagination.",
        examples=[42],
    )
    knowledge_count: int = Field(description="Number of knowledge items.", examples=[40])
    resume_count: int = Field(description="Number of resumes.", examples=[2])
    by_kind: list[VaultKindStatisticsResponseSchema] = Field(
        description="By kind returned by this operation.",
    )
    created_last_30_days_count: int = Field(
        description="Number of items created during the last 30 days.",
        examples=[8],
    )
    created_or_updated_last_30_days_count: int = Field(
        description="Number of items created or updated during the last 30 days.",
        examples=[14],
    )

    @classmethod
    def from_domain_schema(cls, *, schema: VaultStatistics) -> VaultStatisticsResponseSchema:
        return cls.model_construct(
            total_count=schema.total_count,
            knowledge_count=schema.knowledge_count,
            resume_count=schema.resume_count,
            by_kind=[
                VaultKindStatisticsResponseSchema.from_domain_schema(schema=v)
                for v in schema.by_kind
            ],
            created_last_30_days_count=schema.created_last_30_days_count,
            created_or_updated_last_30_days_count=schema.created_or_updated_last_30_days_count,
        )
