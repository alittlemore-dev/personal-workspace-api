from dataclasses import dataclass
from datetime import date, timedelta

from verbose_http_exceptions import BadRequestHTTPException

from entrypoints.litestar.api.parameters import (
    CalendarEndDateQuery,
    CalendarStartDateQuery,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CalendarOccurrenceWindow:
    start_date: date
    end_date: date


def provide_calendar_occurrence_window(
    start_date: CalendarStartDateQuery,
    end_date: CalendarEndDateQuery,
) -> CalendarOccurrenceWindow:
    if start_date >= end_date:
        raise BadRequestHTTPException(message="endDate must follow startDate")
    if end_date - start_date > timedelta(days=420):
        raise BadRequestHTTPException(message="Calendar range must be at most 420 days")
    return CalendarOccurrenceWindow(start_date=start_date, end_date=end_date)
