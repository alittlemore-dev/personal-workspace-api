from dataclasses import dataclass

from core.schemas import Secret


@dataclass(frozen=True, slots=True, kw_only=True)
class User:
    username: str


@dataclass(frozen=True, slots=True, kw_only=True)
class OwnerCredentials:
    username: str
    password_hash: Secret[str]


@dataclass(frozen=True, slots=True, kw_only=True)
class LoginParams:
    username: str
    password: Secret[str]
