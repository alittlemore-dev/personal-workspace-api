from collections.abc import Iterable

from dishka import Provider
from dishka.integrations.litestar import LitestarProvider

from infra.ioc.prodivers.auth_provider import AuthProvider
from infra.ioc.prodivers.calendar_provider import CalendarProvider
from infra.ioc.prodivers.database_provider import DatabaseProvider
from infra.ioc.prodivers.files_provider import FilesProvider
from infra.ioc.prodivers.general_provider import GeneralProvider
from infra.ioc.prodivers.healthcheck_provider import HealthcheckProvider
from infra.ioc.prodivers.knowledge import (
    KnowledgeDatesProvider,
    KnowledgeFilesProvider,
    KnowledgeItemsProvider,
    KnowledgePeopleProvider,
)
from infra.ioc.prodivers.response_cache_warm_provider import ResponseCacheWarmProvider
from infra.ioc.prodivers.resumes_provider import ResumesProvider
from infra.ioc.prodivers.wiki_links_provider import WikiLinksProvider


def get_providers() -> Iterable[Provider]:
    return (
        AuthProvider(),
        GeneralProvider(),
        FilesProvider(),
        DatabaseProvider(),
        LitestarProvider(),
        CalendarProvider(),
        ResumesProvider(),
        KnowledgeItemsProvider(),
        KnowledgeFilesProvider(),
        KnowledgeDatesProvider(),
        KnowledgePeopleProvider(),
        WikiLinksProvider(),
        ResponseCacheWarmProvider(),
        HealthcheckProvider(),
    )
