from unittest.mock import AsyncMock, Mock

from dishka import Provider, Scope, provide

from core.account_time_zone.clients import AccountTimeZoneReader
from core.calendar.occurrences import CalendarOccurrencesUseCase
from core.calendar.use_cases import CalendarUseCase
from core.events.use_cases import EventsUseCase
from core.important_info.use_cases import ImportantInfoUseCase


class MockCalendarProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_account_time_zone_reader(self) -> AccountTimeZoneReader:
        reader = AsyncMock(spec=AccountTimeZoneReader)
        reader.get_time_zone.return_value = "UTC"
        return reader

    @provide(scope=Scope.APP)
    async def provide_calendar_occurrences_use_case(self) -> CalendarOccurrencesUseCase:
        return Mock(spec=CalendarOccurrencesUseCase)

    @provide(scope=Scope.APP)
    async def provide_events_use_case(self) -> EventsUseCase:
        return Mock(spec=EventsUseCase)

    @provide(scope=Scope.APP)
    async def provide_important_info_use_case(self) -> ImportantInfoUseCase:
        return Mock(spec=ImportantInfoUseCase)

    @provide(scope=Scope.APP)
    async def provide_calendar_use_case(self) -> CalendarUseCase:
        return Mock(spec=CalendarUseCase)
