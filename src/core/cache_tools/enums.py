from enum import StrEnum


class CacheDomainEnum(StrEnum):
    HEALTHCHECK = "healthcheck"


class CacheWarmOperationStatusEnum(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
