from datetime import datetime
from typing import Annotated

from pydantic import Field

from core.cache_tools.enums import CacheDomainEnum, CacheWarmOperationStatusEnum
from core.cache_tools.schemas import (
    CacheDomainStatus,
    CacheToolsStatus,
    CacheWarmOperation,
    CacheWarmSummary,
)
from entrypoints.litestar.api.schemas import CamelCaseSchema


class CacheWarmSummaryResponseSchema(CamelCaseSchema):
    attempted: Annotated[
        int,
        Field(
            title="Attempted cache targets",
            description="Number of cache targets attempted.",
            examples=[30],
        ),
    ]
    written: Annotated[
        int,
        Field(
            title="Written cache targets",
            description="Number of cache entries written.",
            examples=[28],
        ),
    ]
    skipped: Annotated[
        int,
        Field(
            title="Skipped cache targets",
            description="Number of cache targets skipped.",
            examples=[2],
        ),
    ]

    @classmethod
    def from_domain_schema(
        cls,
        *,
        schema: CacheWarmSummary,
    ) -> CacheWarmSummaryResponseSchema:
        return cls.model_construct(
            attempted=schema.attempted,
            written=schema.written,
            skipped=schema.skipped,
        )


class CacheWarmOperationResponseSchema(CamelCaseSchema):
    operation_id: Annotated[
        str,
        Field(
            title="Cache warm operation ID",
            description="Identifier used to poll this background operation.",
            examples=["4e92d4de561f4bc7a3eed227868952db"],
        ),
    ]
    status: Annotated[
        CacheWarmOperationStatusEnum,
        Field(
            title="Cache warm status",
            description="Status; allowed values are listed in the referenced enumeration.",
            examples=["queued"],
        ),
    ]
    queued_at: Annotated[
        datetime,
        Field(
            title="Queue timestamp",
            description="Time the operation was queued.",
            examples=["2026-10-18T09:00:00Z"],
        ),
    ]
    summary: Annotated[
        CacheWarmSummaryResponseSchema | None,
        Field(
            title="Completed cache warm summary",
            description="Final warm-run counts; null while the operation is queued or running.",
            examples=[{"attempted": 30, "written": 28, "skipped": 2}],
        ),
    ]

    @classmethod
    def from_domain_schema(
        cls,
        *,
        schema: CacheWarmOperation,
    ) -> CacheWarmOperationResponseSchema:
        return cls.model_construct(
            operation_id=schema.operation_id,
            status=schema.status,
            queued_at=schema.queued_at,
            summary=(
                CacheWarmSummaryResponseSchema.from_domain_schema(schema=schema.summary)
                if schema.summary is not None
                else None
            ),
        )


class CacheDomainStatusResponseSchema(CamelCaseSchema):
    domain: Annotated[
        CacheDomainEnum,
        Field(
            title="Cache domain",
            description="Domain; allowed values are listed in the referenced enumeration.",
            examples=["healthcheck"],
        ),
    ]
    key_count: Annotated[
        int,
        Field(
            title="Current key count",
            description="Number of current cache keys in this domain.",
            examples=[28],
        ),
    ]
    minimum_remaining_ttl_seconds: Annotated[
        int | None,
        Field(
            title="Minimum remaining key TTL in seconds",
            description="Shortest remaining key lifetime; null when there are no expiring keys.",
            examples=[1800],
        ),
    ]
    non_expiring_key_count: Annotated[
        int,
        Field(
            title="Non-expiring key count",
            description="Number of keys without an expiration time.",
            examples=[0],
        ),
    ]

    @classmethod
    def from_domain_schema(
        cls,
        *,
        schema: CacheDomainStatus,
    ) -> CacheDomainStatusResponseSchema:
        return cls.model_construct(
            domain=schema.domain,
            key_count=schema.key_count,
            minimum_remaining_ttl_seconds=schema.minimum_remaining_ttl_seconds,
            non_expiring_key_count=schema.non_expiring_key_count,
        )


class CacheStatusResponseSchema(CamelCaseSchema):
    enabled: Annotated[
        bool,
        Field(
            title="Response cache enabled",
            description="Whether response caching is enabled.",
            examples=[True],
        ),
    ]
    configured_ttl_seconds: Annotated[
        int,
        Field(
            title="Configured response cache TTL",
            description="Configured response cache lifetime in seconds.",
            examples=[3600],
        ),
    ]
    scheduled_warm_interval_seconds: Annotated[
        int,
        Field(
            title="Scheduled cache warm interval in seconds",
            description="Configured interval between scheduled cache warm runs.",
            examples=[900],
        ),
    ]
    domains: Annotated[
        list[CacheDomainStatusResponseSchema],
        Field(title="Cache domains", description="Domains returned by this operation."),
    ]
    last_manual_warm_operation: Annotated[
        CacheWarmOperationResponseSchema | None,
        Field(
            title="Last manual cache warm operation",
            description="Last manual warm operation; see the nested schema for its fields.",
        ),
    ]

    @classmethod
    def from_domain_schema(
        cls,
        *,
        schema: CacheToolsStatus,
    ) -> CacheStatusResponseSchema:
        return cls.model_construct(
            enabled=schema.enabled,
            configured_ttl_seconds=schema.configured_ttl_seconds,
            scheduled_warm_interval_seconds=schema.scheduled_warm_interval_seconds,
            domains=[
                CacheDomainStatusResponseSchema.from_domain_schema(schema=domain)
                for domain in schema.domains
            ],
            last_manual_warm_operation=(
                CacheWarmOperationResponseSchema.from_domain_schema(
                    schema=schema.last_manual_warm_operation,
                )
                if schema.last_manual_warm_operation is not None
                else None
            ),
        )
