from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from core.important_info.storages import ImportantInfoStorage
from core.important_info.use_cases import ImportantInfoUseCase
from infra.postgresql.storages.important_info import ImportantInfoDatabaseStorage


class ImportantInfoProvider(Provider):
    @provide(scope=Scope.REQUEST)
    async def provide_important_info_storage(self, session: AsyncSession) -> ImportantInfoStorage:
        return ImportantInfoDatabaseStorage(session=session)

    @provide(scope=Scope.REQUEST)
    async def provide_important_info_use_case(
        self,
        storage: ImportantInfoStorage,
    ) -> ImportantInfoUseCase:
        return ImportantInfoUseCase(storage=storage)
