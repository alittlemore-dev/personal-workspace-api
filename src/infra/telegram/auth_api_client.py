from dataclasses import dataclass, field

import httpx

from core.telegram.exceptions import TelegramServiceError
from core.telegram.storages import TelegramAccountSettingsReader


@dataclass(frozen=True, slots=True, kw_only=True)
class TelegramAuthApiClientConfig:
    url: str
    service_secret: str = field(repr=False)


@dataclass(kw_only=True, slots=True)
class TelegramAuthApiSettingsReader(TelegramAccountSettingsReader):
    http_client: httpx.AsyncClient
    config: TelegramAuthApiClientConfig

    async def is_enabled(self, *, owner_username: str) -> bool:
        try:
            response = await self.http_client.post(
                self.config.url,
                headers={"X-Telegram-Service-Secret": self.config.service_secret},
                json={"ownerUsername": owner_username},
            )
        except httpx.RequestError as exc:
            raise TelegramServiceError from exc
        if response.status_code != httpx.codes.OK:
            raise TelegramServiceError
        try:
            payload = response.json()
        except ValueError as exc:
            raise TelegramServiceError from exc
        if not isinstance(payload, dict):
            raise TelegramServiceError
        available = payload.get("available")
        enabled = payload.get("enabled")
        if not isinstance(available, bool) or not isinstance(enabled, bool):
            raise TelegramServiceError
        return available and enabled
