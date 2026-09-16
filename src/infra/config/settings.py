from ipaddress import IPv4Address
from typing import Annotated, Literal

from litestar.config.response_cache import CACHE_FOREVER
from pydantic import Field, PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.files.types import Namespace
from core.i18n.enums import LanguageEnum
from core.schemas import Secret
from infra.config.constants import constants

_LOCAL_ALL_INTERFACES_HOST = IPv4Address(0).compressed


class ProjectBaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=constants.path.env_file, extra="ignore")


class SecretStrExtended(SecretStr):
    def to_domain_secret(self) -> Secret[str]:
        return Secret(self.get_secret_value())


class DatabaseSettings(ProjectBaseSettings):
    model_config = SettingsConfigDict(env_prefix="DB_")

    user: str
    password: SecretStrExtended
    driver: str
    host: str
    port: str
    name: str
    pool_pre_ping: bool
    pool_size: int
    max_overflow: int
    expire_on_commit: bool
    log_query_metrics: bool
    slow_query_log_threshold_ms: int
    slow_query_log_statement_max_length: int

    @property
    def url(self) -> SecretStrExtended:
        return SecretStrExtended(
            f"{self.driver}://{self.user}:{self.password.get_secret_value()}@{self.host}:{self.port}/{self.name}",
        )


class AppSettings(ProjectBaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_")

    url_schema: Literal["http", "https"]
    debug: bool
    secret_key: SecretStrExtended
    domain: str
    use_cache: bool

    @property
    def is_local_domain(self) -> bool:
        return self.domain in {"localhost", "127.0.0.1", _LOCAL_ALL_INTERFACES_HOST}

    @property
    def base_url(self) -> str:
        postfix = ":8000" if self.debug and self.is_local_domain else ""
        return f"{self.url_schema}://{self.domain}{postfix}"

    @property
    def public_origin(self) -> str:
        return f"{self.url_schema}://{self.domain}"

    def get_url(self, path: str) -> str:
        return f"{self.base_url}/{path.removeprefix('/')}"

    def get_cache_duration(
        self,
        value: bool | int | type[CACHE_FOREVER],  # noqa: FBT001
    ) -> bool | int | type[CACHE_FOREVER]:
        if self.use_cache:
            return value
        return 0


class MinioSettings(ProjectBaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINIO_")

    host: str
    port: int
    region: str
    secret_key: SecretStrExtended
    access_key: str
    secure: bool
    public_url: str
    cors_max_age_seconds: int

    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def internal_endpoint_url(self) -> str:
        schema = "https" if self.secure else "http"
        return f"{schema}://{self.endpoint}"

    @property
    def public_endpoint_url(self) -> str:
        return self.public_url.rstrip("/")

    def get_object_url(self, object_path: str, bucket: Namespace) -> str:
        return f"{self.public_endpoint_url}/{bucket}/{object_path.removeprefix('/')}"


class FilesSettings(ProjectBaseSettings):
    model_config = SettingsConfigDict(env_prefix="FILES_")

    orphan_retention_seconds: Annotated[PositiveInt, Field(ge=604_800)]


class SentrySettings(ProjectBaseSettings):
    model_config = SettingsConfigDict(env_prefix="SENTRY_")

    use: bool
    dsn: str


class ValkeySettings(ProjectBaseSettings):
    model_config = SettingsConfigDict(env_prefix="VALKEY_")

    host: str
    port: int

    def get_url(self, db: int | str) -> SecretStrExtended:
        return SecretStrExtended(f"valkey://{self.host}:{self.port}/{db}")

    @property
    def url_for_http_cache(self) -> SecretStrExtended:
        return self.get_url(db=constants.valkey.databases.response_cache)


class I18nSettings(ProjectBaseSettings):
    model_config = SettingsConfigDict(env_prefix="I18N_")

    default_language: LanguageEnum


class TaskiqSettings(ProjectBaseSettings):
    model_config = SettingsConfigDict(env_prefix="TASKIQ_")

    cache_warm_interval_seconds: PositiveInt
    file_orphan_prune_interval_seconds: PositiveInt
    result_expire_seconds: PositiveInt


class Settings:
    app: AppSettings
    database: DatabaseSettings
    files: FilesSettings
    i18n: I18nSettings
    minio: MinioSettings
    sentry: SentrySettings
    taskiq: TaskiqSettings
    valkey: ValkeySettings

    def __init__(self) -> None:
        self.app = AppSettings()
        self.database = DatabaseSettings()
        self.files = FilesSettings()
        self.i18n = I18nSettings()
        self.minio = MinioSettings()
        self.sentry = SentrySettings()
        self.taskiq = TaskiqSettings()
        self.valkey = ValkeySettings()


settings = Settings()
