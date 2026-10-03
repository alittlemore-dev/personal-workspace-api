from backend_sdk import Principal
from backend_sdk.integrations.litestar import AuthContext
from dishka import FromDishka
from dishka.integrations.litestar import DishkaRouter
from litestar import Controller, Request, delete, get, post, put, status_codes
from litestar.datastructures import State
from litestar.di import (
    NamedDependency,
    Provide,
)

from core.important_info.schemas import (
    CreateImportantInfoParams,
    ImportantInfoTargetParams,
    SetImportantInfoOrderParams,
    UpdateImportantInfoParams,
)
from core.important_info.use_cases import ImportantInfoUseCase
from entrypoints.litestar.api.important_info.dependencies import (
    provide_create_item_params,
    provide_delete_item_params,
    provide_set_order_params,
    provide_update_item_params,
)
from entrypoints.litestar.api.important_info.schemas import (
    ImportantInfoListResponseSchema,
    ImportantInfoResponseSchema,
)
from infra.config.constants import constants


class ImportantInfoApiController(Controller):
    path = "/important-info"
    tags = ["important info"]
    response_headers = {
        constants.knowledge_files.cache_control_header_name: (
            constants.knowledge_files.no_store_header_value
        ),
    }

    @get("", status_code=status_codes.HTTP_200_OK)
    async def list_items(
        self,
        request: Request[Principal, AuthContext, State],
        use_case: FromDishka[ImportantInfoUseCase],
    ) -> ImportantInfoListResponseSchema:
        return ImportantInfoListResponseSchema.from_domain_schema(
            items=await use_case.list_items(author_username=request.user.username),
        )

    @post(
        "",
        status_code=status_codes.HTTP_201_CREATED,
        dependencies={
            "params": Provide(provide_create_item_params, sync_to_thread=False),
        },
    )
    async def create_item(
        self,
        use_case: FromDishka[ImportantInfoUseCase],
        params: NamedDependency[CreateImportantInfoParams],
    ) -> ImportantInfoResponseSchema:
        return ImportantInfoResponseSchema.from_domain_schema(
            schema=await use_case.create_item(
                params=params,
            ),
        )

    @put(
        "/order",
        status_code=status_codes.HTTP_200_OK,
        dependencies={
            "params": Provide(provide_set_order_params, sync_to_thread=False),
        },
    )
    async def set_order(
        self,
        use_case: FromDishka[ImportantInfoUseCase],
        params: NamedDependency[SetImportantInfoOrderParams],
    ) -> ImportantInfoListResponseSchema:
        return ImportantInfoListResponseSchema.from_domain_schema(
            items=await use_case.set_order(
                params=params,
            ),
        )

    @put(
        "/{item_id:str}",
        status_code=status_codes.HTTP_200_OK,
        dependencies={
            "params": Provide(provide_update_item_params, sync_to_thread=False),
        },
    )
    async def update_item(
        self,
        use_case: FromDishka[ImportantInfoUseCase],
        params: NamedDependency[UpdateImportantInfoParams],
    ) -> ImportantInfoResponseSchema:
        return ImportantInfoResponseSchema.from_domain_schema(
            schema=await use_case.update_item(
                params=params,
            ),
        )

    @delete(
        "/{item_id:str}",
        status_code=status_codes.HTTP_204_NO_CONTENT,
        dependencies={
            "params": Provide(provide_delete_item_params, sync_to_thread=False),
        },
    )
    async def delete_item(
        self,
        use_case: FromDishka[ImportantInfoUseCase],
        params: NamedDependency[ImportantInfoTargetParams],
    ) -> None:
        await use_case.delete_item(
            params=params,
        )


api_router = DishkaRouter("", route_handlers=[ImportantInfoApiController])
