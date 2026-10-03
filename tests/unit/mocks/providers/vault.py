from unittest.mock import Mock

from dishka import Provider, Scope, provide

from core.vault.use_cases import VaultUseCase


class MockVaultProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_vault_use_case(self) -> VaultUseCase:
        return Mock(spec=VaultUseCase)
