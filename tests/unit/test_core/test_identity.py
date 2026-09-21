from core.identity import UserIdentity


def test_user_identity_is_an_immutable_value_object() -> None:
    identity = UserIdentity(username="owner")

    assert identity == UserIdentity(username="owner")
