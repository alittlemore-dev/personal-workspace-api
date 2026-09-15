from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, cast

import pytest
from litestar.exceptions import ImproperlyConfiguredException
from litestar.stores.base import Store

from core.cache_tools.enums import CacheDomainEnum
from entrypoints.litestar.api.healthcheck.endpoints import HealthcheckController
from entrypoints.litestar.api.i18n.endpoints import I18nApiController
from entrypoints.litestar.cli.commands.cache import invalidate_cache_command
from entrypoints.litestar.response_cache import (
    ResponseCacheDomain,
    ResponseCacheDomainStore,
    invalidate_response_cache_domain_for_mutation,
)
from infra.config.constants import constants
from infra.config.settings import settings
from infra.post_commit_actions import PostCommitActions


@dataclass
class FakeStore:
    values: dict[str, bytes] = field(default_factory=dict)
    delete_all_count: int = 0

    async def set(
        self,
        key: str,
        value: str | bytes,
        expires_in: int | timedelta | None = None,
    ) -> None:
        _ = expires_in
        self.values[key] = value if isinstance(value, bytes) else value.encode()

    async def get(self, key: str, renew_for: int | timedelta | None = None) -> bytes | None:
        _ = renew_for
        return self.values.get(key)

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def delete_all(self) -> None:
        self.delete_all_count += 1
        self.values.clear()

    async def exists(self, key: str) -> bool:
        return key in self.values

    async def expires_in(self, key: str) -> int | None:
        return 60 if key in self.values else None


class FakeStores:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.requested_names: list[str] = []

    def get(self, name: str) -> Store:
        self.requested_names.append(name)
        return self.store


class FakeApp:
    def __init__(self, store: Store) -> None:
        self.stores = FakeStores(store=store)


class FakeQueryParams:
    def dict(self) -> dict[str, str]:
        return {"language": "ru"}


class FakeUrl:
    path = "/api/i18n/bundles/ru"


class FakeRequest:
    method = "GET"
    url = FakeUrl()
    query_params = FakeQueryParams()


class TestResponseCacheDomainStore:
    async def test_routes_values_to_the_selected_current_domain(self) -> None:
        health_store = FakeStore()
        i18n_store = FakeStore()
        store = ResponseCacheDomainStore(
            stores={
                ResponseCacheDomain.HEALTHCHECK: cast("Store", health_store),
                ResponseCacheDomain.I18N: cast("Store", i18n_store),
            },
        )

        await store.set("i18n:GET/api/i18n/languages", b"i18n")

        assert await i18n_store.get("GET/api/i18n/languages") == b"i18n"
        assert health_store.values == {}
        assert await store.get("i18n:GET/api/i18n/languages") == b"i18n"

    async def test_clear_domains_accepts_only_current_cache_enum(self) -> None:
        i18n_store = FakeStore(values={"GET/api/i18n/languages": b"i18n"})
        store = ResponseCacheDomainStore(
            stores={ResponseCacheDomain.I18N: cast("Store", i18n_store)},
        )

        await store.clear_domains(domains=(CacheDomainEnum.I18N,))

        assert i18n_store.values == {}
        assert i18n_store.delete_all_count == 1

    @pytest.mark.parametrize("key", ["missing-prefix", "unknown:GET/api/value"])
    async def test_rejects_malformed_or_unknown_domain_keys(self, key: str) -> None:
        store = ResponseCacheDomainStore(stores={})

        with pytest.raises(ImproperlyConfiguredException):
            await store.get(key)


class TestResponseCacheCommands:
    async def test_cli_invalidation_deletes_all_current_domain_stores(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        health_store = FakeStore(values={"health": b"ok"})
        i18n_store = FakeStore(values={"bundle": b"ru"})
        domain_store = ResponseCacheDomainStore(
            stores={
                ResponseCacheDomain.HEALTHCHECK: cast("Store", health_store),
                ResponseCacheDomain.I18N: cast("Store", i18n_store),
            },
        )
        app = FakeApp(store=cast("Store", domain_store))
        monkeypatch.setattr(settings.app, "use_cache", True)

        await invalidate_cache_command(app=cast("Any", app))

        assert app.stores.requested_names == [constants.response_cache.store_name]
        assert health_store.delete_all_count == 1
        assert i18n_store.delete_all_count == 1

    async def test_mutation_invalidates_then_enqueues_warm_only_after_commit(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        events: list[str] = []
        monkeypatch.setattr(settings.app, "use_cache", True)

        async def fake_invalidate_response_cache_domain(
            *,
            request: object,
            domain: ResponseCacheDomain,
        ) -> None:
            _ = request
            events.append(f"invalidate:{domain.value}")

        async def fake_cache_warm_domain_kiq(domain_value: str) -> None:
            events.append(f"enqueue:{domain_value}")

        monkeypatch.setattr(
            "entrypoints.litestar.response_cache.invalidate_response_cache_domain",
            fake_invalidate_response_cache_domain,
        )
        monkeypatch.setattr(
            "entrypoints.taskiq.cache_warm.tasks.cache_warm_domain.kiq",
            fake_cache_warm_domain_kiq,
            raising=False,
        )
        post_commit_actions = PostCommitActions(actions=[])

        await invalidate_response_cache_domain_for_mutation(
            request=cast("Any", object()),
            domain=ResponseCacheDomain.I18N,
            post_commit_actions=post_commit_actions,
        )

        assert events == []

        await post_commit_actions.run()

        assert events == ["invalidate:i18n", "enqueue:i18n"]

    async def test_disabled_cache_does_not_schedule_post_commit_work(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings.app, "use_cache", False)
        post_commit_actions = PostCommitActions(actions=[])

        await invalidate_response_cache_domain_for_mutation(
            request=cast("Any", object()),
            domain=ResponseCacheDomain.I18N,
            post_commit_actions=post_commit_actions,
        )

        assert post_commit_actions.actions == []


class TestResponseCacheRouteConfiguration:
    def test_i18n_handlers_use_i18n_domain_cache(self) -> None:
        for handler in (
            I18nApiController.list_languages,
            I18nApiController.get_bundle,
        ):
            assert handler.cache == settings.app.get_cache_duration(
                constants.response_cache.default_ttl_seconds,
            )
            assert handler.cache_key_builder is not None
            assert handler.cache_key_builder(cast("Any", FakeRequest())).startswith("i18n:")

    def test_health_and_readiness_have_distinct_cache_policies(self) -> None:
        assert HealthcheckController.health.cache == settings.app.get_cache_duration(1)
        assert HealthcheckController.health.cache_key_builder is not None
        assert HealthcheckController.ready.cache is False
