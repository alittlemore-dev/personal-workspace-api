from core.exceptions import DomainError


class AssetPermissionError(DomainError):
    message = "Additional permission required for this operation"
