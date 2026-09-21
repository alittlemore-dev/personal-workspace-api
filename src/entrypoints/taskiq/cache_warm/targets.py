from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import urlencode

from entrypoints.litestar.api.schemas import CamelCaseSchema
from entrypoints.litestar.response_cache import ResponseCacheDomain
from infra.config.constants import constants


@dataclass(frozen=True, slots=True)
class CacheWarmTarget:
    domain: ResponseCacheDomain
    path: str
    query: tuple[tuple[str, str], ...]
    response: CamelCaseSchema

    def build_cache_key(self) -> str:
        query_string = urlencode(sorted(self.query), doseq=True)
        return (
            f"{self.domain.value}"
            f"{constants.response_cache.domain_key_separator}"
            f"GET{self.path}{query_string}"
        )

    def response_cache_payload(self) -> bytes:
        return self.response.response_cache_payload()


@dataclass(frozen=True, slots=True)
class ResponseCacheWarmTargetCollector:
    async def collect(self, *, domains: Iterable[ResponseCacheDomain]) -> list[CacheWarmTarget]:
        _ = domains
        return []
