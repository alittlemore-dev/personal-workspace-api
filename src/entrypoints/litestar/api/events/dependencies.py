from zoneinfo import ZoneInfo

from backend_sdk import Principal
from backend_sdk.integrations.litestar import AuthContext
from dishka import FromDishka
from dishka.integrations.litestar import inject
from litestar import Request
from litestar.datastructures import State
from litestar.di import NamedDependency
from verbose_http_exceptions import BadRequestHTTPException

from core.account_time_zone.clients import AccountTimeZoneReader
from core.events.exceptions import InvalidEventDataError
from core.events.schemas import (
    CreateEventParams,
    EventTargetParams,
    UpdateEventParams,
)
from entrypoints.litestar.api.events.schemas import EventRequestSchema
from entrypoints.litestar.api.parameters import EventIdPath


def provide_create_event_params(
    data: EventRequestSchema,
    request: Request[Principal, AuthContext, State],
    account_time_zone: NamedDependency[ZoneInfo],
) -> CreateEventParams:
    try:
        draft = data.to_domain_schema(anchor_time_zone=account_time_zone)
    except InvalidEventDataError as error:
        raise BadRequestHTTPException(message="Invalid event recurrence") from error
    return CreateEventParams(
        draft=draft,
        author_username=request.user.username,
    )


def provide_get_event_params(
    event_id: EventIdPath,
    request: Request[Principal, AuthContext, State],
) -> EventTargetParams:
    return EventTargetParams(
        event_id=event_id,
        author_username=request.user.username,
    )


def provide_update_event_params(
    event_id: EventIdPath,
    data: EventRequestSchema,
    request: Request[Principal, AuthContext, State],
    account_time_zone: NamedDependency[ZoneInfo],
) -> UpdateEventParams:
    try:
        draft = data.to_domain_schema(anchor_time_zone=account_time_zone)
    except InvalidEventDataError as error:
        raise BadRequestHTTPException(message="Invalid event recurrence") from error
    return UpdateEventParams(
        event_id=event_id,
        draft=draft,
        author_username=request.user.username,
    )


def provide_delete_event_params(
    event_id: EventIdPath,
    request: Request[Principal, AuthContext, State],
) -> EventTargetParams:
    return EventTargetParams(
        event_id=event_id,
        author_username=request.user.username,
    )


@inject
async def provide_event_time_zone(
    request: Request[Principal, AuthContext, State],
    account_time_zone_reader: FromDishka[AccountTimeZoneReader],
) -> ZoneInfo:
    return await account_time_zone_reader.get_time_zone(owner_username=request.user.username)
