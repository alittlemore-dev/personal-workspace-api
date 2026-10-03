from datetime import timedelta

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from core.vault.schemas import VaultConfig
from core.vault.storages import VaultStorage
from core.vault.use_cases import VaultUseCase
from infra.config.constants import constants
from infra.postgresql.storages.vault import VaultDatabaseStorage


class VaultProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def provide_storage(self, session: AsyncSession) -> VaultStorage:
        return VaultDatabaseStorage(session=session)

    @provide(scope=Scope.REQUEST)
    def provide_use_case(self, storage: VaultStorage) -> VaultUseCase:
        return VaultUseCase(
            storage=storage,
            config=VaultConfig(
                recent_limit=constants.vault.recent_limit,
                activity_period=timedelta(days=constants.vault.activity_period_days),
            ),
        )
