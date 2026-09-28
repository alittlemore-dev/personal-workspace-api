from abc import ABC, abstractmethod
from zoneinfo import ZoneInfo

from core.exceptions import DomainError


class AccountTimeZoneUnavailableError(DomainError):
    message = "Account time zone is unavailable"


class AccountTimeZoneReader(ABC):
    @abstractmethod
    async def get_time_zone(self, *, owner_username: str) -> ZoneInfo: ...
