from collections.abc import AsyncIterator

import httpx
from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from core.finance.clients import FinanceRateClient
from core.finance.storages import FinanceStorage
from core.finance.use_cases import FinanceUseCase
from infra.config.constants import constants
from infra.http.finance_rates import BankOfRussiaFinanceRateClient
from infra.postgresql.storages.finance import FinanceDatabaseStorage


class FinanceProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_rate_client(self) -> AsyncIterator[FinanceRateClient]:
        async with httpx.AsyncClient(timeout=constants.finance.http_timeout_seconds) as client:
            yield BankOfRussiaFinanceRateClient(http_client=client)

    @provide(scope=Scope.REQUEST)
    def provide_storage(self, session: AsyncSession) -> FinanceStorage:
        return FinanceDatabaseStorage(session=session)

    @provide(scope=Scope.REQUEST)
    def provide_use_case(
        self,
        storage: FinanceStorage,
        rate_client: FinanceRateClient,
    ) -> FinanceUseCase:
        return FinanceUseCase(storage=storage, rate_client=rate_client)
