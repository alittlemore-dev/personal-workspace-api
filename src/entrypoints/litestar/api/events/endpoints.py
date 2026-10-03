from zoneinfo import ZoneInfo

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
from litestar.params import SkipValidation

from core.events.schemas import (
    CreateEventParams,
    EventTargetParams,
    UpdateEventParams,
)
from core.events.use_cases import EventsUseCase
from entrypoints.litestar.api.events.dependencies import (
    provide_create_event_params,
    provide_delete_event_params,
    provide_event_time_zone,
    provide_get_event_params,
    provide_update_event_params,
)
from entrypoints.litestar.api.events.schemas import (
    EventResponseSchema,
    EventsResponseSchema,
)
from infra.config.constants import constants


class EventsApiController(Controller):
    path = "/events"
    tags = ["events"]
    response_headers = {
        constants.knowledge_files.cache_control_header_name: (
            constants.knowledge_files.no_store_header_value
        ),
    }

    @get(
        "",
        status_code=status_codes.HTTP_200_OK,
        dependencies={
            "account_time_zone": Provide(provide_event_time_zone),
        },
    )
    async def list_events(
        self,
        request: Request[Principal, AuthContext, State],
        use_case: FromDishka[EventsUseCase],
        account_time_zone: NamedDependency[ZoneInfo],
    ) -> EventsResponseSchema:
        return EventsResponseSchema.from_domain_schema(
            events=await use_case.list_events(author_username=request.user.username),
            account_time_zone=account_time_zone,
        )

    @post(
        "",
        status_code=status_codes.HTTP_201_CREATED,
        dependencies={
            "params": Provide(provide_create_event_params, sync_to_thread=False),
            "account_time_zone": Provide(provide_event_time_zone),
        },
    )
    async def create_event(
        self,
        use_case: FromDishka[EventsUseCase],
        account_time_zone: NamedDependency[ZoneInfo],
        params: NamedDependency[SkipValidation[CreateEventParams]],
    ) -> EventResponseSchema:
        return EventResponseSchema.from_domain_schema(
            schema=await use_case.create_event(
                params=params,
            ),
            account_time_zone=account_time_zone,
        )

    @get(
        "/{event_id:str}",
        status_code=status_codes.HTTP_200_OK,
        dependencies={
            "params": Provide(provide_get_event_params, sync_to_thread=False),
            "account_time_zone": Provide(provide_event_time_zone),
        },
    )
    async def get_event(
        self,
        use_case: FromDishka[EventsUseCase],
        account_time_zone: NamedDependency[ZoneInfo],
        params: NamedDependency[EventTargetParams],
    ) -> EventResponseSchema:
        return EventResponseSchema.from_domain_schema(
            schema=await use_case.get_event(
                params=params,
            ),
            account_time_zone=account_time_zone,
        )

    @put(
        "/{event_id:str}",
        status_code=status_codes.HTTP_200_OK,
        dependencies={
            "params": Provide(provide_update_event_params, sync_to_thread=False),
            "account_time_zone": Provide(provide_event_time_zone),
        },
    )
    async def update_event(
        self,
        use_case: FromDishka[EventsUseCase],
        account_time_zone: NamedDependency[ZoneInfo],
        params: NamedDependency[SkipValidation[UpdateEventParams]],
    ) -> EventResponseSchema:
        return EventResponseSchema.from_domain_schema(
            schema=await use_case.update_event(
                params=params,
            ),
            account_time_zone=account_time_zone,
        )

    @delete(
        "/{event_id:str}",
        status_code=status_codes.HTTP_204_NO_CONTENT,
        dependencies={
            "params": Provide(provide_delete_event_params, sync_to_thread=False),
        },
    )
    async def delete_event(
        self,
        use_case: FromDishka[EventsUseCase],
        params: NamedDependency[EventTargetParams],
    ) -> None:
        await use_case.delete_event(
            params=params,
        )


api_router = DishkaRouter("", route_handlers=[EventsApiController])
