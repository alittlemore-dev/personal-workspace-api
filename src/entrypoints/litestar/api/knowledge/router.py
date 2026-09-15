from dishka.integrations.litestar import DishkaRouter

from entrypoints.litestar.api.knowledge.dates.endpoints import (
    KnowledgeDatesApiController,
)
from entrypoints.litestar.api.knowledge.files.endpoints import (
    KnowledgeFilesApiController,
)
from entrypoints.litestar.api.knowledge.items.endpoints import (
    KnowledgeTagsApiController,
)
from entrypoints.litestar.api.knowledge.people.endpoints import PeopleApiController

api_router = DishkaRouter(
    "",
    route_handlers=[
        KnowledgeDatesApiController,
        PeopleApiController,
        KnowledgeTagsApiController,
        KnowledgeFilesApiController,
    ],
)
