from enum import StrEnum


class CacheDomainEnum(StrEnum):
    I18N = "i18n"


class CacheWarmOperationStatusEnum(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
