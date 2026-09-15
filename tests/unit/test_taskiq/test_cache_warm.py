from dataclasses import dataclass, field
from datetime import timedelta
from typing import cast

import msgspec
from litestar.stores.base import Store

from core.i18n.enums import LanguageEnum
from entrypoints.litestar.response_cache import ResponseCacheDomain, ResponseCacheDomainStore
from entrypoints.taskiq.cache_warm.service import CacheWarmSummary, ResponseCacheWarmService
from entrypoints.taskiq.cache_warm.targets import (
    I18nCacheWarmTargetCollector,
    ResponseCacheWarmTargetCollector,
)
from entrypoints.taskiq.cache_warm.writer import ResponseCacheWarmWriter
from infra.config.constants import constants


@dataclass
class FakeStore:
    values: dict[str, bytes] = field(default_factory=dict)
    set_calls: list[tuple[str, bytes | str, int | timedelta | None]] = field(
        default_factory=list,
    )

    async def set(
        self,
        key: str,
        value: bytes | str,
        expires_in: int | timedelta | None = None,
    ) -> None:
        self.set_calls.append((key, value, expires_in))
        self.values[key] = value if isinstance(value, bytes) else value.encode()

    async def get(self, key: str, renew_for: int | timedelta | None = None) -> bytes | None:
        _ = renew_for
        return self.values.get(key)

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def delete_all(self) -> None:
        self.values.clear()

    async def exists(self, key: str) -> bool:
        return key in self.values

    async def expires_in(self, key: str) -> int | None:
        return 60 if key in self.values else None


class TestCacheWarmTargetGeneration:
    async def test_collects_only_current_i18n_targets(self) -> None:
        collector = ResponseCacheWarmTargetCollector(
            i18n_collector=I18nCacheWarmTargetCollector(),
        )

        targets = await collector.collect(domains=(ResponseCacheDomain.I18N,))

        assert {(target.domain, target.path, target.query) for target in targets} == {
            (ResponseCacheDomain.I18N, "/api/i18n/languages", ()),
            *{
                (
                    ResponseCacheDomain.I18N,
                    f"/api/i18n/bundles/{language.value}",
                    (),
                )
                for language in LanguageEnum
            },
        }

    async def test_non_warmable_healthcheck_collects_no_targets(self) -> None:
        collector = ResponseCacheWarmTargetCollector(
            i18n_collector=I18nCacheWarmTargetCollector(),
        )

        assert await collector.collect(domains=(ResponseCacheDomain.HEALTHCHECK,)) == []


class TestCacheWarmWriter:
    async def test_writes_litestar_compatible_payload_to_i18n_store(self) -> None:
        i18n_store = FakeStore()
        domain_store = ResponseCacheDomainStore(
            stores={ResponseCacheDomain.I18N: cast("Store", i18n_store)},
        )
        target = I18nCacheWarmTargetCollector().collect()[0]

        await ResponseCacheWarmWriter(store=domain_store).write_target(target)

        assert i18n_store.set_calls[0][0] == "GET/api/i18n/languages"
        assert i18n_store.set_calls[0][2] == constants.response_cache.default_ttl_seconds
        payload = i18n_store.set_calls[0][1]
        assert isinstance(payload, bytes)
        messages = msgspec.msgpack.decode(payload)
        assert messages[0] == {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"application/json"]],
        }


class TestResponseCacheWarmService:
    def service(self, *, use_cache: bool) -> tuple[ResponseCacheWarmService, FakeStore]:
        i18n_store = FakeStore()
        domain_store = ResponseCacheDomainStore(
            stores={ResponseCacheDomain.I18N: cast("Store", i18n_store)},
        )
        return (
            ResponseCacheWarmService(
                target_collector=ResponseCacheWarmTargetCollector(
                    i18n_collector=I18nCacheWarmTargetCollector(),
                ),
                writer=ResponseCacheWarmWriter(store=domain_store),
                use_cache=use_cache,
                supported_domains=(ResponseCacheDomain.I18N,),
            ),
            i18n_store,
        )

    async def test_warm_all_writes_every_i18n_target(self) -> None:
        service, store = self.service(use_cache=True)

        summary = await service.warm_all()

        expected_count = len(LanguageEnum) + 1
        assert summary == CacheWarmSummary(
            attempted=expected_count,
            written=expected_count,
            skipped=0,
        )
        assert len(store.set_calls) == expected_count

    async def test_disabled_cache_skips_without_writing(self) -> None:
        service, store = self.service(use_cache=False)

        summary = await service.warm_domain(domain=ResponseCacheDomain.I18N)

        assert summary == CacheWarmSummary(attempted=0, written=0, skipped=1)
        assert store.set_calls == []

    async def test_unsupported_healthcheck_domain_is_skipped(self) -> None:
        service, store = self.service(use_cache=True)

        summary = await service.warm_domain(domain=ResponseCacheDomain.HEALTHCHECK)

        assert summary == CacheWarmSummary(attempted=0, written=0, skipped=1)
        assert store.set_calls == []
