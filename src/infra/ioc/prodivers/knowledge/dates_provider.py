from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from core.knowledge.dates.storages import KnowledgeDatesStorage
from core.knowledge.dates.use_cases import KnowledgeDatesUseCase
from core.knowledge.files.services import KnowledgeFileCrudService
from core.knowledge.files.storages import KnowledgeFilesStorage
from core.knowledge.items.services import KnowledgeItemCrudService
from core.knowledge.items.storages import KnowledgeItemsStorage
from infra.postgresql.storages.knowledge.dates import KnowledgeDatesDatabaseStorage


class KnowledgeDatesProvider(Provider):
    @provide(scope=Scope.REQUEST)
    async def provide_knowledge_dates_storage(
        self,
        session: AsyncSession,
    ) -> KnowledgeDatesStorage:
        return KnowledgeDatesDatabaseStorage(session=session)

    @provide(scope=Scope.REQUEST)
    async def provide_knowledge_dates_use_case(
        self,
        item_service: KnowledgeItemCrudService,
        item_storage: KnowledgeItemsStorage,
        dates_storage: KnowledgeDatesStorage,
        file_storage: KnowledgeFilesStorage,
        file_service: KnowledgeFileCrudService,
    ) -> KnowledgeDatesUseCase:
        return KnowledgeDatesUseCase(
            item_service=item_service,
            item_storage=item_storage,
            dates_storage=dates_storage,
            file_storage=file_storage,
            file_service=file_service,
        )
