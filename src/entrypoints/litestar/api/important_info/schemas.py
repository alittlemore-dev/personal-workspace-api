from typing import Annotated

from pydantic import AfterValidator, Field

from core.important_info.schemas import ImportantInfo
from entrypoints.litestar.api.important_info.validators import validate_single_line
from entrypoints.litestar.api.schemas import CamelCaseSchema


class ImportantInfoRequestSchema(CamelCaseSchema):
    text: Annotated[str, Field(max_length=255), AfterValidator(validate_single_line)]


class ImportantInfoOrderRequestSchema(CamelCaseSchema):
    ids: Annotated[list[str], Field(title="Every current item ID in display order")]


class ImportantInfoResponseSchema(CamelCaseSchema):
    id: str
    text: str
    position: int

    @classmethod
    def from_domain_schema(cls, *, schema: ImportantInfo) -> ImportantInfoResponseSchema:
        return cls.model_construct(id=schema.id, text=schema.text, position=schema.position)


class ImportantInfoListResponseSchema(CamelCaseSchema):
    items: list[ImportantInfoResponseSchema]

    @classmethod
    def from_domain_schema(cls, *, items: list[ImportantInfo]) -> ImportantInfoListResponseSchema:
        return cls.model_construct(
            items=[ImportantInfoResponseSchema.from_domain_schema(schema=item) for item in items],
        )
