from unittest.mock import Mock

from dishka import Provider, Scope, provide

from core.finance.use_cases import FinanceUseCase


class MockFinanceProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_finance_use_case(self) -> FinanceUseCase:
        return Mock(spec=FinanceUseCase)
