from enum import StrEnum


class TelegramConnectionState(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    REVOKED = "revoked"
    BLOCKED = "blocked"
