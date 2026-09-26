from enum import StrEnum


class ReminderKind(StrEnum):
    BIRTHDAY = "birthday"
    MEMORABLE_DATE = "memorableDate"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "inProgress"
    RETRY = "retry"
    DONE = "done"
    CANCELED = "canceled"
    EXPIRED = "expired"
    FAILED = "failed"
