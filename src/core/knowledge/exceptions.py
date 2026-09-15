from core.exceptions import DomainError, EntryNotFoundError


class KnowledgeItemNotFoundError(EntryNotFoundError):
    message = "Knowledge item not found"


class PersonNotFoundError(EntryNotFoundError):
    message = "Person not found"


class KnowledgeDateNotFoundError(EntryNotFoundError):
    message = "Knowledge date not found"


class KnowledgeTagNotFoundError(EntryNotFoundError):
    message = "Knowledge tag not found"


class PersonRelationshipTypeNotFoundError(EntryNotFoundError):
    message = "Person relationship type not found"


class PersonRelationshipNotFoundError(EntryNotFoundError):
    message = "Person relationship not found"


class KnowledgeFileNotFoundError(EntryNotFoundError):
    message = "Knowledge file not found"


class InvalidKnowledgeDataError(DomainError):
    message = "Invalid knowledge data"


class KnowledgeConflictError(DomainError):
    message = "Knowledge entry is in use or already exists"
