from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from core.knowledge.dates.storages import KnowledgeDatesStorage
from core.knowledge.files.services import KnowledgeFileCrudService
from core.knowledge.files.storages import KnowledgeFilesStorage
from core.knowledge.items.services import KnowledgeItemCrudService
from core.knowledge.items.storages import KnowledgeItemsStorage
from core.knowledge.people.storages import PeopleStorage
from core.knowledge.people.use_cases import (
    PeopleUseCase,
    PersonRelationshipTypesUseCase,
)
from infra.postgresql.storages.knowledge.people import PeopleDatabaseStorage


class KnowledgePeopleProvider(Provider):
    @provide(scope=Scope.REQUEST)
    async def provide_people_storage(self, session: AsyncSession) -> PeopleStorage:
        return PeopleDatabaseStorage(session=session)

    @provide(scope=Scope.REQUEST)
    async def provide_people_use_case(  # noqa: PLR0913
        self,
        item_service: KnowledgeItemCrudService,
        item_storage: KnowledgeItemsStorage,
        people_storage: PeopleStorage,
        dates_storage: KnowledgeDatesStorage,
        file_storage: KnowledgeFilesStorage,
        file_service: KnowledgeFileCrudService,
    ) -> PeopleUseCase:
        return PeopleUseCase(
            item_service=item_service,
            item_storage=item_storage,
            people_storage=people_storage,
            dates_storage=dates_storage,
            file_storage=file_storage,
            file_service=file_service,
        )

    @provide(scope=Scope.REQUEST)
    async def provide_person_relationship_types_use_case(
        self,
        storage: PeopleStorage,
    ) -> PersonRelationshipTypesUseCase:
        return PersonRelationshipTypesUseCase(storage=storage)
