from core.exceptions import DomainError


class InvalidCredentialsError(DomainError):
    message = "Invalid credentials"
