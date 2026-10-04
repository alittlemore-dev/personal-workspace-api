from backend_sdk import Principal
from backend_sdk.integrations.litestar import AuthContext
from dishka import FromDishka
from dishka.integrations.litestar import DishkaRouter
from litestar import Controller, Request, get
from litestar.datastructures import State
from litestar.di import NamedDependency, Provide

from core.vault.schemas import GetVaultStatisticsParams
from core.vault.use_cases import VaultUseCase
from entrypoints.litestar.api.vault.dependencies import provide_statistics_params
from entrypoints.litestar.api.vault.schemas import (
    VaultRecentResponseSchema,
    VaultStatisticsResponseSchema,
)
from infra.config.constants import constants


class VaultApiController(Controller):
    path = "/vault"
    tags = ["vault"]
    response_headers = {
        constants.knowledge_files.cache_control_header_name: (
            constants.knowledge_files.no_store_header_value
        ),
    }

    @get(
        "/recent",
        opt={"pat_permissions": ("workspace.vault.read",)},
        description=("Personal API token permissions: workspace.vault.read."),
    )
    async def recent(
        self,
        request: Request[Principal, AuthContext, State],
        use_case: FromDishka[VaultUseCase],
    ) -> VaultRecentResponseSchema:
        return VaultRecentResponseSchema.from_domain_schema(
            items=await use_case.list_recent(author_username=request.user.username),
        )

    @get(
        "/statistics",
        dependencies={"params": Provide(provide_statistics_params, sync_to_thread=False)},
        opt={"pat_permissions": ("workspace.vault.read",)},
        description=("Personal API token permissions: workspace.vault.read."),
    )
    async def statistics(
        self,
        params: NamedDependency[GetVaultStatisticsParams],
        use_case: FromDishka[VaultUseCase],
    ) -> VaultStatisticsResponseSchema:
        return VaultStatisticsResponseSchema.from_domain_schema(
            schema=await use_case.get_statistics(params=params),
        )


api_router = DishkaRouter("", route_handlers=[VaultApiController])
