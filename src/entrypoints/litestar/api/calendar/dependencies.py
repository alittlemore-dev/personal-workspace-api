from datetime import timedelta

from backend_sdk import Principal
from backend_sdk.integrations.litestar import AuthContext
from litestar import Request
from litestar.datastructures import State
from verbose_http_exceptions import BadRequestHTTPException

from core.calendar.schemas import GetCalendarOccurrencesParams, GetCalendarParams
from entrypoints.litestar.api.parameters import (
    CalendarEndDateQuery,
    CalendarReferenceDateQuery,
    CalendarStartDateQuery,
    CalendarWindowQuery,
)


def provide_get_calendar_params(
    reference_date: CalendarReferenceDateQuery,
    window: CalendarWindowQuery,
    request: Request[Principal, AuthContext, State],
) -> GetCalendarParams:
    return GetCalendarParams(
        reference_date=reference_date,
        window=window,
        author_username=request.user.username,
    )


def provide_get_occurrences_params(
    start_date: CalendarStartDateQuery,
    end_date: CalendarEndDateQuery,
    request: Request[Principal, AuthContext, State],
) -> GetCalendarOccurrencesParams:
    if start_date >= end_date:
        raise BadRequestHTTPException(message="endDate must follow startDate")
    if end_date - start_date > timedelta(days=420):
        raise BadRequestHTTPException(message="Calendar range must be at most 420 days")
    return GetCalendarOccurrencesParams(
        start_date=start_date,
        end_date=end_date,
        author_username=request.user.username,
    )
