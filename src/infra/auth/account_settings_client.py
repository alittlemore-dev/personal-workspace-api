from dataclasses import dataclass, field
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, Field, ValidationError

from core.account_time_zone.clients import (
    AccountTimeZoneReader,
    AccountTimeZoneUnavailableError,
)
from core.telegram.exceptions import TelegramServiceError
from core.telegram.storages import TelegramAccountSettingsReader


class TelegramBotSettings(BaseModel):
    enabled: bool
    notify: bool


class AccountSettingsResponse(BaseModel):
    language: str
    theme: str
    time_zone: ZoneInfo = Field(alias="timeZone")
    telegram_bots: dict[str, TelegramBotSettings] = Field(alias="telegramBots")


@dataclass(frozen=True, slots=True, kw_only=True)
class AccountSettingsClientConfig:
    url: str
    service_secret: str = field(repr=False)
    telegram_available: bool


@dataclass(kw_only=True, slots=True)
class AuthAccountSettingsReader(AccountTimeZoneReader, TelegramAccountSettingsReader):
    http_client: httpx.AsyncClient
    config: AccountSettingsClientConfig

    async def get_time_zone(self, *, owner_username: str) -> ZoneInfo:
        try:
            settings = await self._get_settings(owner_username=owner_username)
        except (httpx.RequestError, ValidationError, ValueError) as error:
            raise AccountTimeZoneUnavailableError from error
        return settings.time_zone

    async def is_enabled(self, *, owner_username: str) -> bool:
        try:
            settings = await self._get_settings(owner_username=owner_username)
            bot = settings.telegram_bots.get("personal-workspace")
        except (httpx.RequestError, ValidationError, ValueError) as error:
            raise TelegramServiceError from error
        return self.config.telegram_available and bot is not None and bot.enabled

    async def can_notify(self, *, owner_username: str) -> bool:
        try:
            settings = await self._get_settings(owner_username=owner_username)
            bot = settings.telegram_bots.get("personal-workspace")
        except (httpx.RequestError, ValidationError, ValueError) as error:
            raise TelegramServiceError from error
        return self.config.telegram_available and bot is not None and bot.enabled and bot.notify

    async def _get_settings(self, *, owner_username: str) -> AccountSettingsResponse:
        response = await self.http_client.get(
            f"{self.config.url.rstrip('/')}/{quote(owner_username, safe='')}/settings",
            headers={"X-Internal-Service-Secret": self.config.service_secret},
        )
        if response.status_code != httpx.codes.OK:
            raise ValueError
        return AccountSettingsResponse.model_validate(response.json())
