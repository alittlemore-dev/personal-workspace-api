from core.exceptions import DomainError, EntryNotFoundError


class EventNotFoundError(EntryNotFoundError):
    message = "Event not found"


class InvalidEventDataError(DomainError):
    message = "Invalid event data"
