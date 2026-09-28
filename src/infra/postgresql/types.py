from zoneinfo import ZoneInfo

from sqlalchemy import String
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class ZoneInfoType(TypeDecorator[ZoneInfo]):
    impl = String(255)
    cache_ok = True

    def process_bind_param(self, value: ZoneInfo | None, _dialect: Dialect) -> str | None:
        if value is None:
            return None
        if value.key is None:
            msg = "Only named IANA time zones can be persisted"
            raise ValueError(msg)
        return value.key

    def process_result_value(self, value: str | None, _dialect: Dialect) -> ZoneInfo | None:
        return ZoneInfo(value) if value is not None else None
