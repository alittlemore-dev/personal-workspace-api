from collections.abc import Generator

import pytest
from pydantic import ValidationError

from core.i18n.enums import LanguageEnum
from infra.config.settings import Settings


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

    def test_i18n_default_language(self) -> None:
        assert self.settings.i18n.default_language == LanguageEnum.RU

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
