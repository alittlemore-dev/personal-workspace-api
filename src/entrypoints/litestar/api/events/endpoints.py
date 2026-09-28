from backend_sdk import Principal
from backend_sdk.integrations.litestar import AuthContext
from dishka import FromDishka
from dishka.integrations.litestar import DishkaRouter
from litestar import Controller, Request, delete, get, post, put, status_codes
from litestar.datastructures import State
from verbose_http_exceptions import BadRequestHTTPException

from core.account_time_zone.clients import AccountTimeZoneReader
from core.events.exceptions import InvalidEventDataError
from core.events.use_cases import EventsUseCase
from entrypoints.litestar.api.events.schemas import (
    EventRequestSchema,
    EventResponseSchema,
    EventsResponseSchema,
)
from entrypoints.litestar.api.parameters import EventIdPath
from infra.config.constants import constants


class EventsApiController(Controller):
    path = "/events"
    tags = ["events"]
    include_in_schema = False
    response_headers = {
        constants.knowledge_files.cache_control_header_name: (
            constants.knowledge_files.no_store_header_value
        ),
    }

    @get("", status_code=status_codes.HTTP_200_OK)
    async def list_events(
        self,
        request: Request[Principal, AuthContext, State],
        use_case: FromDishka[EventsUseCase],
        account_time_zone_reader: FromDishka[AccountTimeZoneReader],
    ) -> EventsResponseSchema:
        account_time_zone = await account_time_zone_reader.get_time_zone(
            owner_username=request.user.username,
        )
        return EventsResponseSchema.from_domain_schema(
            events=await use_case.list_events(author_username=request.user.username),
            account_time_zone=account_time_zone,
        )

    @post("", status_code=status_codes.HTTP_201_CREATED)
    async def create_event(
        self,
        data: EventRequestSchema,
        request: Request[Principal, AuthContext, State],
        use_case: FromDishka[EventsUseCase],
        account_time_zone_reader: FromDishka[AccountTimeZoneReader],
    ) -> EventResponseSchema:
        account_time_zone = await account_time_zone_reader.get_time_zone(
            owner_username=request.user.username,
        )
        try:
            draft = data.to_domain_schema(anchor_time_zone=account_time_zone)
        except InvalidEventDataError as error:
            raise BadRequestHTTPException(message="Invalid event recurrence") from error
        return EventResponseSchema.from_domain_schema(
            schema=await use_case.create_event(
                draft=draft,
                author_username=request.user.username,
            ),
            account_time_zone=account_time_zone,
        )

    @get("/{event_id:str}", status_code=status_codes.HTTP_200_OK)
    async def get_event(
        self,
        event_id: EventIdPath,
        request: Request[Principal, AuthContext, State],
        use_case: FromDishka[EventsUseCase],
        account_time_zone_reader: FromDishka[AccountTimeZoneReader],
    ) -> EventResponseSchema:
        account_time_zone = await account_time_zone_reader.get_time_zone(
            owner_username=request.user.username,
        )
        return EventResponseSchema.from_domain_schema(
            schema=await use_case.get_event(
                event_id=event_id,
                author_username=request.user.username,
            ),
            account_time_zone=account_time_zone,
        )

    @put("/{event_id:str}", status_code=status_codes.HTTP_200_OK)
    async def update_event(
        self,
        event_id: EventIdPath,
        data: EventRequestSchema,
        request: Request[Principal, AuthContext, State],
        use_case: FromDishka[EventsUseCase],
        account_time_zone_reader: FromDishka[AccountTimeZoneReader],
    ) -> EventResponseSchema:
        account_time_zone = await account_time_zone_reader.get_time_zone(
            owner_username=request.user.username,
        )
        try:
            draft = data.to_domain_schema(anchor_time_zone=account_time_zone)
        except InvalidEventDataError as error:
            raise BadRequestHTTPException(message="Invalid event recurrence") from error
        return EventResponseSchema.from_domain_schema(
            schema=await use_case.update_event(
                event_id=event_id,
                draft=draft,
                author_username=request.user.username,
            ),
            account_time_zone=account_time_zone,
        )

    @delete("/{event_id:str}", status_code=status_codes.HTTP_204_NO_CONTENT)
    async def delete_event(
        self,
        event_id: EventIdPath,
        request: Request[Principal, AuthContext, State],
        use_case: FromDishka[EventsUseCase],
    ) -> None:
        await use_case.delete_event(event_id=event_id, author_username=request.user.username)


api_router = DishkaRouter("", route_handlers=[EventsApiController])
