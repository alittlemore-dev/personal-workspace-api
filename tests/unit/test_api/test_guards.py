from typing import Any, cast

import pytest
from litestar.exceptions import NotAuthorizedException

from core.auth.schemas import User
from entrypoints.litestar.guards import require_authenticated_user


class FakeConnection:
    def __init__(self, *, identity: object | None) -> None:
        self.scope = {"user": identity}


class TestAuthenticatedUserGuard:
    def test_allows_nonblank_authenticated_user(self) -> None:
        connection = FakeConnection(identity=User(username="admin"))

        require_authenticated_user(
            cast("Any", connection),
            cast("Any", object()),
        )

    @pytest.mark.parametrize(
        "identity",
        [
            None,
            object(),
            User(username=""),
            User(username="   "),
        ],
    )
    def test_rejects_missing_unverified_or_blank_identity(self, identity: object | None) -> None:
        connection = FakeConnection(identity=identity)

        with pytest.raises(NotAuthorizedException):
            require_authenticated_user(
                cast("Any", connection),
                cast("Any", object()),
            )
