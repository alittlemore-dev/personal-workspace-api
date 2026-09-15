from typing import Annotated

from pydantic import Field

from core.auth.schemas import LoginParams, User
from core.schemas import Secret
from entrypoints.litestar.api.schemas import CamelCaseSchema


class LoginRequestSchema(CamelCaseSchema):
    username: Annotated[str, Field(title="Username", min_length=1)]
    password: Annotated[str, Field(title="Password", min_length=1)]

    def to_domain_schema(self) -> LoginParams:
        return LoginParams(username=self.username, password=Secret(self.password))


class UserResponseSchema(CamelCaseSchema):
    username: Annotated[str, Field(title="Username")]

    @classmethod
    def from_domain_schema(cls, *, schema: User) -> UserResponseSchema:
        return cls.model_construct(username=schema.username)
