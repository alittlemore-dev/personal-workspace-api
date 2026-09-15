import pytest
from argon2 import PasswordHasher as Argon2CryptContext

from core.schemas import Secret
from infra.auth.password_hashers import Argon2PasswordHasher
from tests.helpers.factories.core import TEST_OWNER_PASSWORD, TEST_OWNER_PASSWORD_HASH


def test_verify_accepts_valid_argon2id_hash() -> None:
    hasher = Argon2PasswordHasher(context=Argon2CryptContext())

    result = hasher.verify(
        password=Secret(TEST_OWNER_PASSWORD),
        password_hash=Secret(TEST_OWNER_PASSWORD_HASH),
    )

    assert result is True


@pytest.mark.parametrize(
    "password_hash",
    [
        TEST_OWNER_PASSWORD_HASH,
        "not-an-argon2-hash",
        "$bcrypt$2b$12$not-an-argon2-hash",
    ],
)
def test_verify_returns_false_for_invalid_password_or_hash(password_hash: str) -> None:
    hasher = Argon2PasswordHasher(context=Argon2CryptContext())

    result = hasher.verify(
        password=Secret(
            "wrong-password" if password_hash == TEST_OWNER_PASSWORD_HASH else TEST_OWNER_PASSWORD
        ),
        password_hash=Secret(password_hash),
    )

    assert result is False
