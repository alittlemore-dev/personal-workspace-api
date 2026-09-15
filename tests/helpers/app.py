import uuid
from dataclasses import dataclass
from typing import cast
from unittest.mock import Mock

from dishka import AsyncContainer

from core.cache_tools.schemas import CacheToolsPolicy
from core.cache_tools.use_cases import CacheToolsUseCase
from core.calendar.use_cases import CalendarUseCase
from core.files.file_name_generators import FileNameGenerator
from core.files.services import FileService
from core.generators import HexUuidIdGenerator
from core.knowledge.dates.use_cases import KnowledgeDatesUseCase
from core.knowledge.files.clients import KnowledgeFileObjectCleaner, KnowledgeFileRollbackRegistrar
from core.knowledge.files.use_cases import KnowledgeFilesUseCase
from core.knowledge.items.use_cases import KnowledgeTagsUseCase
from core.knowledge.people.use_cases import PeopleUseCase, PersonRelationshipTypesUseCase
from core.resumes.use_cases import ResumesUseCase
from core.types import IntId
from core.wiki_links.use_cases import WikiLinksUseCase
from infra.healthcheck import ReadinessChecker


@dataclass(kw_only=True)
class IocContainerHelper:
    container: AsyncContainer

    async def get_random_uuid(self) -> uuid.UUID:
        return await self.container.get(uuid.UUID)

    async def get_random_int(self) -> IntId:
        return await self.container.get(IntId)

    async def get_hex_uuid_id_generator(self) -> HexUuidIdGenerator:
        return await self.container.get(HexUuidIdGenerator)

    async def get_wiki_links_use_case(self) -> Mock:
        use_case = await self.container.get(WikiLinksUseCase)
        return cast("Mock", use_case)

    async def get_cache_tools_use_case(self) -> Mock:
        use_case = await self.container.get(CacheToolsUseCase)
        return cast("Mock", use_case)

    async def get_cache_tools_policy(self) -> CacheToolsPolicy:
        return await self.container.get(CacheToolsPolicy)

    async def get_file_name_generator(self) -> Mock:
        generator = await self.container.get(FileNameGenerator)
        return cast("Mock", generator)

    async def get_file_service(self) -> Mock:
        service = await self.container.get(FileService)
        return cast("Mock", service)

    async def get_resumes_use_case(self) -> Mock:
        use_case = await self.container.get(ResumesUseCase)
        return cast("Mock", use_case)

    async def get_people_use_case(self) -> Mock:
        use_case = await self.container.get(PeopleUseCase)
        return cast("Mock", use_case)

    async def get_calendar_use_case(self) -> Mock:
        use_case = await self.container.get(CalendarUseCase)
        return cast("Mock", use_case)

    async def get_knowledge_dates_use_case(self) -> Mock:
        use_case = await self.container.get(KnowledgeDatesUseCase)
        return cast("Mock", use_case)

    async def get_knowledge_files_use_case(self) -> Mock:
        use_case = await self.container.get(KnowledgeFilesUseCase)
        return cast("Mock", use_case)

    async def get_knowledge_file_object_cleaner(self) -> Mock:
        cleaner = await self.container.get(KnowledgeFileObjectCleaner)
        return cast("Mock", cleaner)

    async def get_knowledge_file_rollback_registrar(self) -> Mock:
        registrar = await self.container.get(KnowledgeFileRollbackRegistrar)
        return cast("Mock", registrar)

    async def get_knowledge_tags_use_case(self) -> Mock:
        use_case = await self.container.get(KnowledgeTagsUseCase)
        return cast("Mock", use_case)

    async def get_person_relationship_types_use_case(self) -> Mock:
        use_case = await self.container.get(PersonRelationshipTypesUseCase)
        return cast("Mock", use_case)

    async def get_readiness_checker(self) -> Mock:
        checker = await self.container.get(ReadinessChecker)
        return cast("Mock", checker)
