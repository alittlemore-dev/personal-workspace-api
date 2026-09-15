from argon2 import PasswordHasher as Argon2CryptContext
from dishka import Provider, Scope, provide

from core.auth.password_hashers import PasswordHasher
from core.auth.schemas import OwnerCredentials
from core.auth.use_cases import LoginUseCase
from infra.auth.password_hashers import Argon2PasswordHasher
from infra.config.settings import settings


class AuthProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_owner_credentials(self) -> OwnerCredentials:
        return OwnerCredentials(
            username=settings.owner.username,
            password_hash=settings.owner.password_hash.to_domain_secret(),
        )

    @provide(scope=Scope.APP)
    async def provide_password_hasher(self) -> PasswordHasher:
        return Argon2PasswordHasher(context=Argon2CryptContext())

    @provide(scope=Scope.APP)
    async def provide_login_use_case(
        self,
        password_hasher: PasswordHasher,
        owner: OwnerCredentials,
    ) -> LoginUseCase:
        return LoginUseCase(password_hasher=password_hasher, owner=owner)
