import hashlib
import json
from ipaddress import IPv4Address
from typing import Annotated, Literal
from urllib.parse import urlsplit

from litestar.config.response_cache import CACHE_FOREVER
from pydantic import (
    Field,
    NonNegativeFloat,
    PositiveFloat,
    PositiveInt,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from core.files.types import Namespace
from core.schemas import Secret
from infra.config.constants import constants

_LOCAL_ALL_INTERFACES_HOST = IPv4Address(0).compressed
_MISSING_TELEGRAM_CREDENTIALS = "Telegram credentials and bot username are required when available"
_INVALID_TELEGRAM_PROXY_URLS = (
    "Telegram proxies must be an empty value or a JSON array of distinct socks5/http URLs "
    "with hosts and explicit ports; "
    "encode credentials and omit path, query, and fragment"
)
_ASCII_SPACE = 32


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


class AuthSettings(ProjectBaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_")

    verify_url: str
    account_settings_url: str
    timeout_seconds: PositiveFloat
    cache_ttl_seconds: NonNegativeFloat
    max_cache_entries: PositiveInt


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


class TaskiqSettings(ProjectBaseSettings):
    model_config = SettingsConfigDict(env_prefix="TASKIQ_")

    cache_warm_interval_seconds: PositiveInt
    file_orphan_prune_interval_seconds: PositiveInt
    result_expire_seconds: PositiveInt


class TelegramSettings(ProjectBaseSettings):
    model_config = SettingsConfigDict(env_prefix="TELEGRAM_", hide_input_in_errors=True)

    available: bool = False
    bot_username: str = ""
    bot_token: SecretStrExtended = SecretStrExtended("")
    webhook_secret: SecretStrExtended = SecretStrExtended("")
    service_secret: SecretStrExtended = SecretStrExtended("")
    delivery_mode: Literal["polling", "webhook"]
    proxy_urls: Annotated[list[SecretStrExtended], NoDecode] = Field(repr=False)

    @property
    def proxy_pool_id(self) -> str:
        normalized = json.dumps(
            {
                "routes": [proxy.get_secret_value() for proxy in self.proxy_urls],
                "bot_token": self.bot_token.get_secret_value(),
                "delivery_mode": self.delivery_mode,
            },
            separators=(",", ":"),
        )
        return hashlib.sha256(normalized.encode()).hexdigest()

    @field_validator("proxy_urls", mode="before")
    @classmethod
    def validate_proxy_urls(cls, value: object) -> list[SecretStrExtended]:
        try:
            urls = value
            if isinstance(value, str):
                urls = json.loads(value) if value else []
            if not isinstance(urls, list) or any(
                not isinstance(url, str | SecretStrExtended) for url in urls
            ):
                raise ValueError(_INVALID_TELEGRAM_PROXY_URLS)  # noqa: TRY301
            secrets = [
                url if isinstance(url, SecretStrExtended) else SecretStrExtended(url)
                for url in urls
            ]
            raw_urls = [secret.get_secret_value() for secret in secrets]
            if len(set(raw_urls)) != len(raw_urls):
                raise ValueError(_INVALID_TELEGRAM_PROXY_URLS)  # noqa: TRY301
            for raw_url in raw_urls:
                parsed = urlsplit(raw_url)
                valid = (
                    parsed.scheme in {"socks5", "http"}
                    and bool(parsed.hostname)
                    and parsed.port is not None
                    and parsed.port > 0
                    and parsed.path in {"", "/"}
                    and not parsed.query
                    and not parsed.fragment
                    and not any(
                        character.isspace() or ord(character) < _ASCII_SPACE
                        for character in raw_url
                    )
                    and "\\" not in raw_url
                    and (
                        (parsed.username is None and parsed.password is None)
                        or bool(parsed.username)
                    )
                    and (parsed.username is None or parsed.password is not None)
                )
                if not valid:
                    raise ValueError(_INVALID_TELEGRAM_PROXY_URLS)  # noqa: TRY301
        except ValueError:
            raise ValueError(_INVALID_TELEGRAM_PROXY_URLS) from None
        return secrets

    @model_validator(mode="after")
    def validate_available_configuration(self) -> TelegramSettings:  # noqa: N804
        if self.available and (
            self.bot_username == "configure_bot"
            or not all(
                (
                    self.bot_username,
                    self.bot_token.get_secret_value(),
                    self.webhook_secret.get_secret_value()
                    if self.delivery_mode == "webhook"
                    else True,
                    self.service_secret.get_secret_value(),
                ),
            )
        ):
            raise ValueError(_MISSING_TELEGRAM_CREDENTIALS)
        return self


class Settings:
    app: AppSettings
    auth: AuthSettings
    database: DatabaseSettings
    files: FilesSettings
    minio: MinioSettings
    sentry: SentrySettings
    taskiq: TaskiqSettings
    telegram: TelegramSettings
    valkey: ValkeySettings

    def __init__(self) -> None:
        self.app = AppSettings()
        self.auth = AuthSettings()
        self.database = DatabaseSettings()
        self.files = FilesSettings()
        self.minio = MinioSettings()
        self.sentry = SentrySettings()
        self.taskiq = TaskiqSettings()
        self.telegram = TelegramSettings()
        self.valkey = ValkeySettings()


settings = Settings()
