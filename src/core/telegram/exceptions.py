from core.exceptions import DomainError


class TelegramInvitationError(DomainError):
    message = "Invitation is invalid or expired"


class TelegramAccessError(DomainError):
    message = "Telegram connection is unavailable"


class TelegramLimitError(DomainError):
    message = "Telegram invitation limit reached"


class TelegramServiceError(DomainError):
    message = "Telegram connection service is unavailable"
