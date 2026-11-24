from unittest.mock import Mock

from dishka import Provider, Scope, provide

from core.finance.assets.analytics_use_cases import AssetAnalyticsUseCase
from core.finance.assets.services import AssetMovementService
from core.finance.event_dispatchers import FinanceEventDispatcher
from core.finance.use_cases import FinanceUseCase


class MockFinanceProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_finance_use_case(self) -> FinanceUseCase:
        return Mock(spec=FinanceUseCase)

    @provide(scope=Scope.APP)
    async def provide_analytics(self) -> AssetAnalyticsUseCase:
        return Mock(spec=AssetAnalyticsUseCase)

    @provide(scope=Scope.APP)
    async def provide_movements(self) -> AssetMovementService:
        return Mock(spec=AssetMovementService)

    @provide(scope=Scope.APP)
    async def provide_dispatcher(self) -> FinanceEventDispatcher:
        return Mock(spec=FinanceEventDispatcher)
