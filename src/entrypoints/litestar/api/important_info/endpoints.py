from backend_sdk import Principal
from backend_sdk.integrations.litestar import AuthContext
from dishka import FromDishka
from dishka.integrations.litestar import DishkaRouter
from litestar import Controller, Request, delete, get, post, put, status_codes
from litestar.datastructures import State

from core.important_info.use_cases import ImportantInfoUseCase
from entrypoints.litestar.api.important_info.schemas import (
    ImportantInfoListResponseSchema,
    ImportantInfoOrderRequestSchema,
    ImportantInfoRequestSchema,
    ImportantInfoResponseSchema,
)
from entrypoints.litestar.api.parameters import ImportantInfoIdPath
from infra.config.constants import constants


class ImportantInfoApiController(Controller):
    path = "/important-info"
    tags = ["important info"]
    include_in_schema = False
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

    @post("", status_code=status_codes.HTTP_201_CREATED)
    async def create_item(
        self,
        data: ImportantInfoRequestSchema,
        request: Request[Principal, AuthContext, State],
        use_case: FromDishka[ImportantInfoUseCase],
    ) -> ImportantInfoResponseSchema:
        return ImportantInfoResponseSchema.from_domain_schema(
            schema=await use_case.create_item(
                text=data.text,
                author_username=request.user.username,
            ),
        )

    @put("/order", status_code=status_codes.HTTP_200_OK)
    async def set_order(
        self,
        data: ImportantInfoOrderRequestSchema,
        request: Request[Principal, AuthContext, State],
        use_case: FromDishka[ImportantInfoUseCase],
    ) -> ImportantInfoListResponseSchema:
        return ImportantInfoListResponseSchema.from_domain_schema(
            items=await use_case.set_order(ids=data.ids, author_username=request.user.username),
        )

    @put("/{item_id:str}", status_code=status_codes.HTTP_200_OK)
    async def update_item(
        self,
        item_id: ImportantInfoIdPath,
        data: ImportantInfoRequestSchema,
        request: Request[Principal, AuthContext, State],
        use_case: FromDishka[ImportantInfoUseCase],
    ) -> ImportantInfoResponseSchema:
        return ImportantInfoResponseSchema.from_domain_schema(
            schema=await use_case.update_item(
                item_id=item_id,
                text=data.text,
                author_username=request.user.username,
            ),
        )

    @delete("/{item_id:str}", status_code=status_codes.HTTP_204_NO_CONTENT)
    async def delete_item(
        self,
        item_id: ImportantInfoIdPath,
        request: Request[Principal, AuthContext, State],
        use_case: FromDishka[ImportantInfoUseCase],
    ) -> None:
        await use_case.delete_item(item_id=item_id, author_username=request.user.username)


api_router = DishkaRouter("", route_handlers=[ImportantInfoApiController])
