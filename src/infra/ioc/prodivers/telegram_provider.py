from collections.abc import AsyncIterator

import httpx
from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from core.telegram.generators import InvitationTokenGenerator
from core.telegram.schemas import TelegramUseCaseConfig
from core.telegram.storages import (
    TelegramAccountSettingsReader,
    TelegramRedemptionLimiter,
    TelegramStorage,
    TelegramTransaction,
)
from core.telegram.use_cases import TelegramUseCase
from infra.config.constants import constants
from infra.config.settings import settings
from infra.postgresql.storages.telegram import TelegramDatabaseStorage
from infra.postgresql.telegram_transaction import TelegramDatabaseTransaction
from infra.telegram.auth_api_client import (
    TelegramAuthApiClientConfig,
    TelegramAuthApiSettingsReader,
)
from infra.valkey.telegram_limiter import ValkeyTelegramRedemptionLimiter


class TelegramProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_token_generator(self) -> InvitationTokenGenerator:
        return InvitationTokenGenerator()

    @provide(scope=Scope.APP)
    def provide_telegram_config(self) -> TelegramUseCaseConfig:
        return TelegramUseCaseConfig(
            bot_username=settings.telegram.bot_username,
            invitation_limit=constants.telegram.invitation_limit_per_hour,
            connection_limit=constants.telegram.connection_limit_per_workspace,
            available=settings.telegram.available,
        )

    @provide(scope=Scope.APP)
    async def provide_redemption_limiter(self) -> AsyncIterator[TelegramRedemptionLimiter]:
        valkey_url = settings.valkey.get_url(
            db=constants.valkey.databases.response_cache,
        )
        valkey = Valkey.from_url(valkey_url.get_secret_value())
        try:
            yield ValkeyTelegramRedemptionLimiter(
                valkey=valkey,
                limit=constants.telegram.redemption_attempt_limit,
                window_seconds=constants.telegram.redemption_attempt_window_seconds,
            )
        finally:
            await valkey.aclose(close_connection_pool=True)

    @provide(scope=Scope.APP)
    async def provide_account_settings_reader(self) -> AsyncIterator[TelegramAccountSettingsReader]:
        async with httpx.AsyncClient(timeout=settings.auth.timeout_seconds) as http_client:
            yield TelegramAuthApiSettingsReader(
                http_client=http_client,
                config=TelegramAuthApiClientConfig(
                    url=settings.telegram.auth_api_url,
                    service_secret=settings.telegram.service_secret.get_secret_value(),
                ),
            )

    @provide(scope=Scope.REQUEST)
    def provide_storage(self, session: AsyncSession) -> TelegramStorage:
        return TelegramDatabaseStorage(session=session)

    @provide(scope=Scope.REQUEST)
    def provide_transaction(self, session: AsyncSession) -> TelegramTransaction:
        return TelegramDatabaseTransaction(session=session)

    @provide(scope=Scope.REQUEST)
    def provide_use_case(
        self,
        storage: TelegramStorage,
        settings_reader: TelegramAccountSettingsReader,
        token_generator: InvitationTokenGenerator,
        config: TelegramUseCaseConfig,
        limiter: TelegramRedemptionLimiter,
    ) -> TelegramUseCase:
        return TelegramUseCase(
            storage=storage,
            settings_reader=settings_reader,
            token_generator=token_generator,
            config=config,
            limiter=limiter,
        )
