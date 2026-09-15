from unittest.mock import Mock

from dishka import Provider, Scope, provide

from core.knowledge.dates.use_cases import KnowledgeDatesUseCase
from core.knowledge.files.clients import (
    KnowledgeFileObjectCleaner,
    KnowledgeFileRollbackRegistrar,
)
from core.knowledge.files.use_cases import KnowledgeFilesUseCase
from core.knowledge.items.use_cases import KnowledgeTagsUseCase
from core.knowledge.people.use_cases import (
    PeopleUseCase,
    PersonRelationshipTypesUseCase,
)


class MockKnowledgeProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_knowledge_files_use_case(self) -> KnowledgeFilesUseCase:
        return Mock(spec=KnowledgeFilesUseCase)

    @provide(scope=Scope.APP)
    async def provide_knowledge_file_object_cleaner(self) -> KnowledgeFileObjectCleaner:
        return Mock(spec=KnowledgeFileObjectCleaner)

    @provide(scope=Scope.APP)
    async def provide_knowledge_file_rollback_registrar(
        self,
    ) -> KnowledgeFileRollbackRegistrar:
        return Mock(spec=KnowledgeFileRollbackRegistrar)

    @provide(scope=Scope.APP)
    async def provide_people_use_case(self) -> PeopleUseCase:
        return Mock(spec=PeopleUseCase)

    @provide(scope=Scope.APP)
    async def provide_knowledge_dates_use_case(self) -> KnowledgeDatesUseCase:
        return Mock(spec=KnowledgeDatesUseCase)

    @provide(scope=Scope.APP)
    async def provide_knowledge_tags_use_case(self) -> KnowledgeTagsUseCase:
        return Mock(spec=KnowledgeTagsUseCase)

    @provide(scope=Scope.APP)
    async def provide_person_relationship_types_use_case(
        self,
    ) -> PersonRelationshipTypesUseCase:
        return Mock(spec=PersonRelationshipTypesUseCase)
