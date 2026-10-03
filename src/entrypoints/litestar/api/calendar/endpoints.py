from dishka import FromDishka
from dishka.integrations.litestar import DishkaRouter
from litestar import Controller, get, status_codes
from litestar.di import NamedDependency, Provide

from core.calendar.occurrences import CalendarOccurrencesUseCase
from core.calendar.schemas import (
    GetCalendarOccurrencesParams,
    GetCalendarParams,
)
from core.calendar.use_cases import CalendarUseCase
from entrypoints.litestar.api.calendar.dependencies import (
    provide_get_calendar_params,
    provide_get_occurrences_params,
)
from entrypoints.litestar.api.calendar.schemas import (
    CalendarOccurrencesResponseSchema,
    CalendarResponseSchema,
)
from infra.config.constants import constants


class CalendarApiController(Controller):
    path = "/calendar"
    tags = ["calendar"]
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
        dependencies={"params": Provide(provide_get_calendar_params, sync_to_thread=False)},
    )
    async def get_calendar(
        self,
        use_case: FromDishka[CalendarUseCase],
        params: NamedDependency[GetCalendarParams],
    ) -> CalendarResponseSchema:
        return CalendarResponseSchema.from_domain_schema(
            schema=await use_case.get_calendar(
                params=params,
            ),
        )

    @get(
        "/occurrences",
        status_code=status_codes.HTTP_200_OK,
        cache=False,
        dependencies={
            "params": Provide(provide_get_occurrences_params, sync_to_thread=False),
        },
    )
    async def get_occurrences(
        self,
        use_case: FromDishka[CalendarOccurrencesUseCase],
        params: NamedDependency[GetCalendarOccurrencesParams],
    ) -> CalendarOccurrencesResponseSchema:
        return CalendarOccurrencesResponseSchema.from_domain_schema(
            schema=await use_case.get_occurrences(
                params=params,
            ),
        )


api_router = DishkaRouter("", route_handlers=[CalendarApiController])
