from core.exceptions import EntryNotFoundError


class ResumeNotFoundError(EntryNotFoundError):
    message = "Resume not found"
