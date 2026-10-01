from enum import StrEnum


class TelegramRuntimeStatus(StrEnum):
    DISABLED = "disabled"
    CONNECTING = "connecting"
    READY = "ready"
    FAILED = "failed"


class TelegramConnectionState(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    REVOKED = "revoked"
    BLOCKED = "blocked"
