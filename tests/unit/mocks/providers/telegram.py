from unittest.mock import Mock

from dishka import Provider, Scope, provide

from core.telegram.storages import TelegramTransaction
from core.telegram.use_cases import TelegramUseCase


class MockTelegramProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_telegram_use_case(self) -> TelegramUseCase:
        return Mock(spec=TelegramUseCase)

    @provide(scope=Scope.APP)
    async def provide_telegram_transaction(self) -> TelegramTransaction:
        return Mock(spec=TelegramTransaction)
