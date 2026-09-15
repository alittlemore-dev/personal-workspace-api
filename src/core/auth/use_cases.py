import hmac

from core.auth.exceptions import InvalidCredentialsError
from core.auth.password_hashers import PasswordHasher
from core.auth.schemas import LoginParams, OwnerCredentials, User


class LoginUseCase:
    def __init__(self, *, password_hasher: PasswordHasher, owner: OwnerCredentials) -> None:
        self.password_hasher = password_hasher
        self.owner = owner

    def execute(self, *, params: LoginParams) -> User:
        username_matches = hmac.compare_digest(
            params.username.encode(),
            self.owner.username.encode(),
        )
        password_matches = self.password_hasher.verify(
            password=params.password,
            password_hash=self.owner.password_hash,
        )
        if not username_matches or not password_matches:
            raise InvalidCredentialsError
        return User(username=self.owner.username)
