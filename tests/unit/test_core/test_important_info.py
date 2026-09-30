from unittest.mock import AsyncMock, Mock

import pytest

from core.important_info.exceptions import InvalidImportantInfoOrderError
from core.important_info.schemas import (
    ImportantInfo,
    SetImportantInfoOrderParams,
)
from core.important_info.storages import ImportantInfoStorage
from core.important_info.use_cases import ImportantInfoUseCase


@pytest.mark.asyncio
async def test_order_rejects_missing_duplicate_and_foreign_ids_before_writing() -> None:
    storage = Mock(spec=ImportantInfoStorage)
    storage.list_items = AsyncMock(
        return_value=[
            ImportantInfo(id="a" * 32, text="A", position=0),
            ImportantInfo(id="b" * 32, text="B", position=1),
        ],
    )
    use_case = ImportantInfoUseCase(storage=storage)

    for ids in [["a" * 32], ["a" * 32, "a" * 32], ["a" * 32, "c" * 32]]:
        with pytest.raises(InvalidImportantInfoOrderError):
            await use_case.set_order(
                params=SetImportantInfoOrderParams(
                    ids=ids,
                    author_username="owner",
                ),
            )
    storage.set_order.assert_not_called()

    storage.set_order.return_value = [
        ImportantInfo(id="b" * 32, text="B", position=0),
        ImportantInfo(id="a" * 32, text="A", position=1),
    ]
    result = await use_case.set_order(
        params=SetImportantInfoOrderParams(
            ids=["b" * 32, "a" * 32],
            author_username="owner",
        ),
    )
    assert [item.id for item in result] == ["b" * 32, "a" * 32]
    storage.set_order.assert_awaited_once_with(ids=["b" * 32, "a" * 32], author_username="owner")
