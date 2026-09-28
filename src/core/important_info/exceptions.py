from core.exceptions import DomainError, EntryNotFoundError


class ImportantInfoNotFoundError(EntryNotFoundError):
    message = "Important info not found"


class InvalidImportantInfoOrderError(DomainError):
    message = "Order must contain every current important info ID exactly once"
