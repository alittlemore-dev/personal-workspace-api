from datetime import datetime
from typing import Annotated

from litestar.params import PathParameter
from pydantic import Field, field_validator

from core.telegram.schemas import TelegramConnection, TelegramInvitation
from entrypoints.litestar.api.schemas import CamelCaseSchema

TelegramItemId = Annotated[str, PathParameter()]


class TelegramLabelRequest(CamelCaseSchema):
    label: Annotated[str, Field(min_length=1, max_length=100)]

    @field_validator("label")
    @classmethod
    def strip_nonblank_label(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            message = "Label must not be blank"
            raise ValueError(message)
        return stripped


class TelegramInvitationResponse(CamelCaseSchema):
    id: str
    label: str
    expires_at: datetime

    @classmethod
    def from_domain_schema(cls, schema: TelegramInvitation) -> TelegramInvitationResponse:
        return cls(id=schema.id, label=schema.label, expires_at=schema.expires_at)


class TelegramConnectionResponse(CamelCaseSchema):
    id: str
    label: str
    telegram_user_id: int
    username: str
    first_name: str
    state: str
    requested_at: datetime
    connected_at: datetime | None
    last_contact_at: datetime

    @classmethod
    def from_domain_schema(cls, schema: TelegramConnection) -> TelegramConnectionResponse:
        return cls(
            id=schema.id,
            label=schema.label,
            telegram_user_id=schema.telegram_user_id,
            username=schema.username,
            first_name=schema.first_name,
            state=schema.state.value,
            requested_at=schema.requested_at,
            connected_at=schema.connected_at,
            last_contact_at=schema.last_contact_at,
        )


class TelegramSettingsResponse(CamelCaseSchema):
    available: bool
    invitations: list[TelegramInvitationResponse]
    connections: list[TelegramConnectionResponse]


class TelegramIssuedInvitationResponse(CamelCaseSchema):
    url: str
    expires_at: datetime
