from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from core.knowledge.items.services import KnowledgeItemCrudService
from core.knowledge.items.storages import KnowledgeItemsStorage
from core.knowledge.items.use_cases import KnowledgeTagsUseCase
from infra.postgresql.storages.knowledge.items import KnowledgeItemsDatabaseStorage


class KnowledgeItemsProvider(Provider):
    @provide(scope=Scope.REQUEST)
    async def provide_knowledge_items_storage(
        self,
        session: AsyncSession,
    ) -> KnowledgeItemsStorage:
        return KnowledgeItemsDatabaseStorage(session=session)

    @provide(scope=Scope.REQUEST)
    async def provide_knowledge_item_crud_service(
        self,
        storage: KnowledgeItemsStorage,
    ) -> KnowledgeItemCrudService:
        return KnowledgeItemCrudService(storage=storage)

    @provide(scope=Scope.REQUEST)
    async def provide_knowledge_tags_use_case(
        self,
        storage: KnowledgeItemsStorage,
    ) -> KnowledgeTagsUseCase:
        return KnowledgeTagsUseCase(storage=storage)
