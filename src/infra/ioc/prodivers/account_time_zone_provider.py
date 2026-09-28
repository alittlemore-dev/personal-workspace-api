from collections.abc import AsyncIterator

import httpx
from dishka import Provider, Scope, provide

from core.account_time_zone.clients import AccountTimeZoneReader
from infra.auth.account_settings_client import (
    AccountSettingsClientConfig,
    AuthAccountSettingsReader,
)
from infra.config.settings import settings


class AccountTimeZoneProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_auth_account_settings_reader(
        self,
    ) -> AsyncIterator[AuthAccountSettingsReader]:
        async with httpx.AsyncClient(timeout=settings.auth.timeout_seconds) as http_client:
            yield AuthAccountSettingsReader(
                http_client=http_client,
                config=AccountSettingsClientConfig(
                    url=settings.auth.account_settings_url,
                    service_secret=settings.telegram.service_secret.get_secret_value(),
                    telegram_available=settings.telegram.available,
                ),
            )

    @provide(scope=Scope.APP)
    def provide_account_time_zone_reader(
        self,
        settings_reader: AuthAccountSettingsReader,
    ) -> AccountTimeZoneReader:
        return settings_reader
