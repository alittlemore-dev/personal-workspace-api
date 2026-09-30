from core.exceptions import DomainError, EntryNotFoundError


class FinanceNotFoundError(EntryNotFoundError):
    message = "Finance entry not found"


class InvalidFinanceDataError(DomainError):
    message = "Invalid finance data"


class FinanceConflictError(DomainError):
    message = "Finance entry changed; reload and try again"


class FinanceRateUnavailableError(DomainError):
    message = "Exchange rate unavailable; try again later"
