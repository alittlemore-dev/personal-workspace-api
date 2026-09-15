from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import urlencode

from core.i18n.enums import LanguageEnum
from entrypoints.litestar.api.i18n.catalog import get_i18n_messages, get_language_label
from entrypoints.litestar.api.i18n.schemas import (
    I18nBundleResponseSchema,
    LanguageResponseSchema,
    LanguagesResponseSchema,
)
from entrypoints.litestar.api.schemas import CamelCaseSchema
from entrypoints.litestar.response_cache import ResponseCacheDomain
from infra.config.constants import constants
from infra.config.settings import settings


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
class I18nCacheWarmTargetCollector:
    def collect(self) -> list[CacheWarmTarget]:
        return [
            self._languages_target(),
            *[self._bundle_target(language=language) for language in LanguageEnum],
        ]

    def _languages_target(self) -> CacheWarmTarget:
        return CacheWarmTarget(
            domain=ResponseCacheDomain.I18N,
            path="/api/i18n/languages",
            query=(),
            response=LanguagesResponseSchema(
                default_language=settings.i18n.default_language,
                languages=[
                    LanguageResponseSchema.from_language(
                        language=language,
                        label=get_language_label(language=language),
                    )
                    for language in LanguageEnum
                ],
            ),
        )

    def _bundle_target(self, *, language: LanguageEnum) -> CacheWarmTarget:
        return CacheWarmTarget(
            domain=ResponseCacheDomain.I18N,
            path=f"/api/i18n/bundles/{language.value}",
            query=(),
            response=I18nBundleResponseSchema(
                language=language,
                messages=dict(get_i18n_messages(language=language)),
            ),
        )


@dataclass(frozen=True, slots=True)
class ResponseCacheWarmTargetCollector:
    i18n_collector: I18nCacheWarmTargetCollector

    async def collect(self, *, domains: Iterable[ResponseCacheDomain]) -> list[CacheWarmTarget]:
        if ResponseCacheDomain.I18N in domains:
            return self.i18n_collector.collect()
        return []
