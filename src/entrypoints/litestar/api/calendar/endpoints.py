from backend_sdk import Principal
from backend_sdk.integrations.litestar import AuthContext
from dishka import FromDishka
from dishka.integrations.litestar import DishkaRouter
from litestar import Controller, Request, get, status_codes
from litestar.datastructures import State
from litestar.di import NamedDependency, Provide

from core.calendar.occurrences import CalendarOccurrencesUseCase
from core.calendar.use_cases import CalendarUseCase
from entrypoints.litestar.api.calendar.dependencies import (
    CalendarOccurrenceWindow,
    provide_calendar_occurrence_window,
)
from entrypoints.litestar.api.calendar.schemas import (
    CalendarOccurrencesResponseSchema,
    CalendarResponseSchema,
)
from entrypoints.litestar.api.parameters import CalendarReferenceDateQuery, CalendarWindowQuery
from infra.config.constants import constants


class CalendarApiController(Controller):
    path = "/calendar"
    tags = ["calendar"]
    include_in_schema = False
    response_headers = {
        constants.knowledge_files.cache_control_header_name: (
            constants.knowledge_files.no_store_header_value
        ),
    }

    @get(
        "",
        description=(
            "Get the current author's memorable dates and birthdays for the selected calendar "
            "window."
        ),
        name="calendar-api-handler",
        status_code=status_codes.HTTP_200_OK,
        cache=False,
    )
    async def get_calendar(
        self,
        reference_date: CalendarReferenceDateQuery,
        window: CalendarWindowQuery,
        request: Request[Principal, AuthContext, State],
        use_case: FromDishka[CalendarUseCase],
    ) -> CalendarResponseSchema:
        return CalendarResponseSchema.from_domain_schema(
            schema=await use_case.get_calendar(
                reference_date=reference_date,
                window=window,
                author_username=request.user.username,
            ),
        )

    @get(
        "/occurrences",
        status_code=status_codes.HTTP_200_OK,
        cache=False,
        dependencies={
            "window": Provide(provide_calendar_occurrence_window, sync_to_thread=False),
        },
    )
    async def get_occurrences(
        self,
        window: NamedDependency[CalendarOccurrenceWindow],
        request: Request[Principal, AuthContext, State],
        use_case: FromDishka[CalendarOccurrencesUseCase],
    ) -> CalendarOccurrencesResponseSchema:
        return CalendarOccurrencesResponseSchema.from_domain_schema(
            schema=await use_case.get_occurrences(
                start_date=window.start_date,
                end_date=window.end_date,
                author_username=request.user.username,
            ),
        )


api_router = DishkaRouter("", route_handlers=[CalendarApiController])
