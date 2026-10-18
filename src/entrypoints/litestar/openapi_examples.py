from typing import Any

from litestar.openapi.spec import Example


class JSONExample(Example):
    def to_schema(self) -> dict[str, Any]:
        result = super().to_schema()
        # Litestar removes null dictionary entries, including required nullable JSON fields.
        if self.value is not None:
            result["value"] = self.value
        return result
