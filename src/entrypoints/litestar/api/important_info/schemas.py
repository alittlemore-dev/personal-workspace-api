from typing import Annotated

from pydantic import AfterValidator, Field

from core.important_info.schemas import ImportantInfo
from entrypoints.litestar.api.important_info.validators import validate_single_line
from entrypoints.litestar.api.schemas import CamelCaseSchema


class ImportantInfoRequestSchema(CamelCaseSchema):
    text: Annotated[
        str,
        Field(
            max_length=255,
            description="Single-line note, up to 255 characters.",
            examples=["Passport renewal appointment on 25 October"],
        ),
        AfterValidator(validate_single_line),
    ]


class ImportantInfoOrderRequestSchema(CamelCaseSchema):
    ids: Annotated[
        list[str],
        Field(
            title="Every current item ID in display order",
            description=(
                "Every current item identifier exactly once, in the desired display order."
            ),
            examples=[["4e92d4de561f4bc7a3eed227868952db"]],
        ),
    ]


class ImportantInfoResponseSchema(CamelCaseSchema):
    id: str = Field(
        description="Opaque resource identifier; use the value returned by this API.",
        examples=["4e92d4de561f4bc7a3eed227868952db"],
    )
    text: str = Field(
        description="Single-line note, up to 255 characters.",
        examples=["Passport renewal appointment on 25 October"],
    )
    position: int = Field(description="Zero-based position in display order.", examples=[0])

    @classmethod
    def from_domain_schema(cls, *, schema: ImportantInfo) -> ImportantInfoResponseSchema:
        return cls.model_construct(id=schema.id, text=schema.text, position=schema.position)


class ImportantInfoListResponseSchema(CamelCaseSchema):
    items: list[ImportantInfoResponseSchema] = Field(
        description="Items returned by this operation.",
    )

    @classmethod
    def from_domain_schema(cls, *, items: list[ImportantInfo]) -> ImportantInfoListResponseSchema:
        return cls.model_construct(
            items=[ImportantInfoResponseSchema.from_domain_schema(schema=item) for item in items],
        )
