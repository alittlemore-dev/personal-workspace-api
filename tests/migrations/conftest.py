from collections.abc import Generator

import pytest

from infra.postgresql.utils import downgrade, migrate


@pytest.fixture
def migrated_to_0001() -> Generator[None]:
    migrate(revision="0001")
    yield
    downgrade(revision="base")
