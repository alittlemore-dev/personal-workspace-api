from unittest.mock import Mock

from dishka import Provider, Scope, provide

from core.calendar.use_cases import CalendarUseCase


class MockCalendarProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_calendar_use_case(self) -> CalendarUseCase:
        return Mock(spec=CalendarUseCase)
