from core.vault.schemas import VaultEntry, VaultKindStatistics, VaultStatistics
from entrypoints.litestar.api.schemas import CamelCaseSchema


class VaultEntryResponseSchema(CamelCaseSchema):
    id: str
    source: str
    kind: str
    display_name: str
    updated_at: str

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
    items: list[VaultEntryResponseSchema]

    @classmethod
    def from_domain_schema(cls, *, items: list[VaultEntry]) -> VaultRecentResponseSchema:
        return cls.model_construct(
            items=[VaultEntryResponseSchema.from_domain_schema(schema=item) for item in items],
        )


class VaultKindStatisticsResponseSchema(CamelCaseSchema):
    source: str
    kind: str
    total_count: int

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
    total_count: int
    knowledge_count: int
    resume_count: int
    by_kind: list[VaultKindStatisticsResponseSchema]
    created_last_30_days_count: int
    created_or_updated_last_30_days_count: int

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
