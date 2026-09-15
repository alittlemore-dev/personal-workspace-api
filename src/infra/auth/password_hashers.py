from dataclasses import dataclass

from argon2 import PasswordHasher as Argon2CryptContext
from argon2.exceptions import InvalidHashError, VerificationError

from core.auth.password_hashers import PasswordHasher
from core.schemas import Secret
from infra.config.constants import constants


@dataclass(frozen=True, slots=True, kw_only=True)
class Argon2PasswordHasher(PasswordHasher):
    context: Argon2CryptContext

    def verify(self, *, password: Secret[str], password_hash: Secret[str]) -> bool:
        password_hash_value = password_hash.get_secret_value()
        if not password_hash_value.startswith(constants.auth.argon2id_hash_prefix):
            return False
        try:
            return self.context.verify(
                password_hash_value,
                password.get_secret_value(),
            )
        except InvalidHashError, VerificationError:
            return False

    def hash(self, *, password: Secret[str]) -> str:
        return self.context.hash(password.get_secret_value())
