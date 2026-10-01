import json
import traceback
from collections.abc import Generator
from pathlib import Path

import pytest
from pydantic import ValidationError

from infra.config.settings import SecretStrExtended, Settings, TelegramSettings


class TestSettings:
    @pytest.fixture(autouse=True)
    def setup(self, test_settings: Settings) -> Generator[None]:
        self.settings = test_settings
        orig = self.settings.app.domain
        orig_debug = self.settings.app.debug
        orig_public_url = self.settings.minio.public_url
        self.settings.app.domain = "alittlemoron.ru"
        self.settings.app.url_schema = "https"
        self.settings.app.debug = False
        self.settings.minio.public_url = "https://s3.alittlemoron.ru"
        yield
        self.settings.app.domain = orig
        self.settings.app.debug = orig_debug
        self.settings.app.url_schema = "http"
        self.settings.minio.public_url = orig_public_url

    def test_app_base_url(self) -> None:
        assert self.settings.app.base_url == "https://alittlemoron.ru"

    def test_app_base_url_adds_debug_port_for_local_domain(self) -> None:
        self.settings.app.domain = "localhost"
        self.settings.app.debug = True
        assert self.settings.app.base_url == "https://localhost:8000"

    def test_app_public_origin_ignores_debug_port(self) -> None:
        self.settings.app.debug = True
        assert self.settings.app.public_origin == "https://alittlemoron.ru"

    def test_app_get_url(self) -> None:
        assert self.settings.app.get_url(path="/api/healthcheck/ready") == (
            "https://alittlemoron.ru/api/healthcheck/ready"
        )

    def test_minio_region(self) -> None:
        assert self.settings.minio.region == "us-east-1"

    def test_minio_public_endpoint_url_trims_trailing_slash(self) -> None:
        self.settings.minio.public_url = "https://s3.alittlemoron.ru/"
        assert self.settings.minio.public_endpoint_url == "https://s3.alittlemoron.ru"

    def test_minio_get_object_url(self) -> None:
        assert (
            self.settings.minio.get_object_url(bucket="media", object_path="test.txt")
            == "https://s3.alittlemoron.ru/media/test.txt"
        )

    def test_minio_get_object_url_object_path_startswith_slash(self) -> None:
        assert (
            self.settings.minio.get_object_url(bucket="media", object_path="/test.txt")
            == "https://s3.alittlemoron.ru/media/test.txt"
        )

    def test_valkey_get_url(self) -> None:
        self.settings.valkey.host = "localhost"
        self.settings.valkey.port = 6379
        assert self.settings.valkey.get_url(db=0).get_secret_value() == "valkey://localhost:6379/0"
        assert (
            self.settings.valkey.url_for_http_cache.get_secret_value()
            == "valkey://localhost:6379/0"
        )

    def test_taskiq_file_orphan_prune_interval_is_required(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("TASKIQ_FILE_ORPHAN_PRUNE_INTERVAL_SECONDS")

        with pytest.raises(ValidationError, match="file_orphan_prune_interval_seconds"):
            type(self.settings.taskiq)(
                _env_file=None,
                cache_warm_interval_seconds=3_600,
                result_expire_seconds=3_600,
            )

    def test_file_orphan_retention_is_required_and_at_least_seven_days(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("FILES_ORPHAN_RETENTION_SECONDS")

        with pytest.raises(ValidationError, match="orphan_retention_seconds"):
            type(self.settings.files)(_env_file=None)

        with pytest.raises(ValidationError, match="greater than or equal to 604800"):
            type(self.settings.files)(_env_file=None, orphan_retention_seconds=0)

        with pytest.raises(ValidationError, match="greater than or equal to 604800"):
            type(self.settings.files)(_env_file=None, orphan_retention_seconds=604_799)


class TestTelegramSettings:
    @pytest.mark.parametrize(
        "proxy_urls",
        [
            "",
            "[]",
            '["socks5://proxy.test:1080"]',
            '["socks5://proxy.test:1080", "http://user:pass%40word@backup.test:3128/"]',
        ],
    )
    def test_proxy_list_accepts_supported_transports_and_empty_direct_mode(
        self,
        proxy_urls: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TELEGRAM_PROXY_URLS", proxy_urls)
        config = TelegramSettings(_env_file=None)
        expected = json.loads(proxy_urls) if proxy_urls else []
        assert [proxy.get_secret_value() for proxy in config.proxy_urls] == expected
        assert all(isinstance(proxy, SecretStrExtended) for proxy in config.proxy_urls)
        assert proxy_urls == "" or proxy_urls not in repr(config)
        for proxy in expected:
            assert proxy not in repr(config.proxy_urls)
            assert proxy not in config.model_dump_json()

    def test_proxy_list_accepts_secret_items_without_unwrapping_them(self) -> None:
        proxy = SecretStrExtended("socks5://user:PRIVATE_PASSWORD@proxy.test:1080")
        config = TelegramSettings(_env_file=None, proxy_urls=[proxy])
        assert config.proxy_urls == [proxy]
        assert config.proxy_urls[0] is proxy
        assert "PRIVATE_PASSWORD" not in repr(config.proxy_urls)

    @pytest.mark.parametrize(
        "proxy_url",
        [
            "https://user:PRIVATE_PASSWORD@proxy.test:443",
            "mtproto://user:PRIVATE_PASSWORD@proxy.test:443",
            "socks5://user:PRIVATE_PASSWORD@proxy.test",
            "socks5://user:PRIVATE_PASSWORD@proxy.test:65536",
            "socks5://user:PRIVATE_PASSWORD@proxy.test:0",
            "socks5://user:PRIVATE_PASSWORD@:1080",
            "socks5://user:PRIVATE_PASSWORD@proxy.test:1080/path",
            "socks5://user:PRIVATE_PASSWORD@proxy.test:1080?option=true",
            "socks5://user:PRIVATE_PASSWORD@proxy.test:1080#fragment",
            "socks5://user:PRIVATE_PASSWORD@proxy.test:1080\n",
            "socks5://user@proxy.test:1080",
        ],
    )
    def test_invalid_proxy_url_is_rejected_without_exposing_credentials(
        self,
        proxy_url: str,
    ) -> None:
        with pytest.raises(ValidationError, match="Telegram proxies") as error:
            TelegramSettings(
                _env_file=None,
                proxy_urls=[SecretStrExtended(proxy_url)],
            )
        assert "PRIVATE_PASSWORD" not in str(error.value)
        assert proxy_url not in str(error.value)

    def test_proxy_configuration_requires_explicit_direct_or_proxy_choice(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("TELEGRAM_PROXY_URLS")
        with pytest.raises(ValidationError, match="proxy_urls"):
            TelegramSettings(_env_file=None)

    @pytest.mark.parametrize(
        "raw_value",
        [
            "socks5://proxy.test:1080",
            '"socks5://proxy.test:1080"',
            "null",
            "{}",
            '[""]',
            "[null]",
            "[123]",
            '[{"password": "PRIVATE_PASSWORD"}]',
            '["socks5://proxy.test:1080", "socks5://proxy.test:1080"]',
        ],
    )
    def test_invalid_proxy_list_is_rejected_without_exposing_input(
        self,
        raw_value: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TELEGRAM_PROXY_URLS", raw_value)
        with pytest.raises(ValidationError, match="Telegram proxies") as error:
            TelegramSettings(_env_file=None)
        assert raw_value not in str(error.value)
        assert "PRIVATE_PASSWORD" not in str(error.value)

    @pytest.mark.parametrize("source", ["environment", "dotenv"])
    @pytest.mark.parametrize(
        "raw_value",
        [
            '["socks5://user:PRIVATE_PASSWORD@proxy.test:1080"',
            '["https://user:PRIVATE_PASSWORD@proxy.test:443"]',
        ],
    )
    def test_proxy_source_errors_hide_credentials_in_traceback(
        self,
        source: str,
        raw_value: str,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        if source == "environment":
            monkeypatch.setenv("TELEGRAM_PROXY_URLS", raw_value)
            env_file = None
        else:
            monkeypatch.delenv("TELEGRAM_PROXY_URLS")
            env_file = tmp_path / ".env"
            env_file.write_text(f"TELEGRAM_PROXY_URLS='{raw_value}'\n")
        with pytest.raises(ValidationError, match="Telegram proxies") as error:
            TelegramSettings(_env_file=env_file)
        formatted = "".join(traceback.format_exception(error.value))
        assert "PRIVATE_PASSWORD" not in formatted
        assert raw_value not in formatted

    def test_route_fingerprint_ignores_json_formatting_but_changes_with_pool(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TELEGRAM_PROXY_URLS", '["socks5://proxy.test:1080"]')
        compact = TelegramSettings(_env_file=None)
        monkeypatch.setenv("TELEGRAM_PROXY_URLS", '[ "socks5://proxy.test:1080" ]')
        formatted = TelegramSettings(_env_file=None)
        other = TelegramSettings(
            _env_file=None,
            proxy_urls=[SecretStrExtended("socks5://backup.test:1080")],
        )
        assert compact.proxy_pool_id == formatted.proxy_pool_id
        assert compact.proxy_pool_id != other.proxy_pool_id
        rotated_token = compact.model_copy(
            update={"bot_token": SecretStrExtended("654321:ROTATED_TEST_TOKEN")},
        )
        assert compact.proxy_pool_id != rotated_token.proxy_pool_id

    def test_telegram_requires_service_secret_when_available(self) -> None:
        with pytest.raises(ValidationError):
            TelegramSettings(
                _env_file=None,
                available=True,
                bot_username="alittlemore_workspace_bot",
                bot_token=SecretStrExtended("123456:BOT_TOKEN"),
                webhook_secret=SecretStrExtended("WEBHOOK_SECRET"),
                service_secret=SecretStrExtended(""),
            )

    def test_telegram_cannot_be_available_without_bot_credentials(self) -> None:
        with pytest.raises(ValidationError):
            TelegramSettings(
                available=True,
                bot_username="",
                bot_token=SecretStrExtended(""),
                webhook_secret=SecretStrExtended(""),
            )

    def test_telegram_cannot_be_available_with_placeholder_username(self) -> None:
        with pytest.raises(ValidationError):
            TelegramSettings(
                available=True,
                bot_username="configure_bot",
                bot_token=SecretStrExtended("123456:BOT_TOKEN"),
                webhook_secret=SecretStrExtended("WEBHOOK_SECRET"),
            )
