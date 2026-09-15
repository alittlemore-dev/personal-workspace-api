from dataclasses import dataclass, field

import pytest

from core.auth.exceptions import InvalidCredentialsError
from core.auth.password_hashers import PasswordHasher
from core.auth.schemas import LoginParams, OwnerCredentials, User
from core.auth.use_cases import LoginUseCase
from core.schemas import Secret
from tests.helpers.factories.core import (
    TEST_OWNER_PASSWORD,
    TEST_OWNER_PASSWORD_HASH,
    TEST_OWNER_USERNAME,
)


@dataclass
class PasswordHasherSpy(PasswordHasher):
    verification_result: bool
    verification_calls: list[tuple[Secret[str], Secret[str]]] = field(default_factory=list)

    def verify(self, *, password: Secret[str], password_hash: Secret[str]) -> bool:
        self.verification_calls.append((password, password_hash))
        return self.verification_result


def test_execute_returns_owner_for_matching_credentials() -> None:
    password_hasher = PasswordHasherSpy(verification_result=True)
    use_case = LoginUseCase(
        password_hasher=password_hasher,
        owner=owner_credentials(),
    )

    result = use_case.execute(
        params=LoginParams(
            username=TEST_OWNER_USERNAME,
            password=Secret(TEST_OWNER_PASSWORD),
        ),
    )

    assert result == User(username=TEST_OWNER_USERNAME)


@pytest.mark.parametrize(
    ("username", "verification_result"),
    [
        ("wrong-owner", True),
        (TEST_OWNER_USERNAME, False),
    ],
)
def test_execute_rejects_invalid_credentials_with_same_generic_error(
    username: str,
    verification_result: bool,
) -> None:
    password_hasher = PasswordHasherSpy(verification_result=verification_result)
    use_case = LoginUseCase(
        password_hasher=password_hasher,
        owner=owner_credentials(),
    )

    with pytest.raises(InvalidCredentialsError) as exc_info:
        use_case.execute(
            params=LoginParams(username=username, password=Secret(TEST_OWNER_PASSWORD)),
        )

    assert str(exc_info.value) == InvalidCredentialsError.message


def test_execute_verifies_password_when_username_does_not_match() -> None:
    password_hasher = PasswordHasherSpy(verification_result=True)
    owner = owner_credentials()
    use_case = LoginUseCase(password_hasher=password_hasher, owner=owner)
    password = Secret(TEST_OWNER_PASSWORD)

    with pytest.raises(InvalidCredentialsError):
        use_case.execute(
            params=LoginParams(username="wrong-owner", password=password),
        )

    assert password_hasher.verification_calls == [(password, owner.password_hash)]


def test_execute_rejects_non_ascii_username_after_password_verification() -> None:
    password_hasher = PasswordHasherSpy(verification_result=True)
    owner = owner_credentials()
    use_case = LoginUseCase(password_hasher=password_hasher, owner=owner)
    password = Secret(TEST_OWNER_PASSWORD)

    with pytest.raises(InvalidCredentialsError):
        use_case.execute(
            params=LoginParams(username="владелец", password=password),
        )

    assert password_hasher.verification_calls == [(password, owner.password_hash)]


def owner_credentials() -> OwnerCredentials:
    return OwnerCredentials(
        username=TEST_OWNER_USERNAME,
        password_hash=Secret(TEST_OWNER_PASSWORD_HASH),
    )
