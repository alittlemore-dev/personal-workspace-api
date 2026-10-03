from datetime import datetime
from typing import Annotated

from litestar.openapi.spec import Example
from litestar.params import PathParameter
from pydantic import Field, field_validator

from core.i18n.enums import LanguageEnum
from core.telegram.enums import TelegramRuntimeStatus
from core.telegram.schemas import (
    TelegramConnection,
    TelegramConnectionSettings,
    TelegramInvitation,
)
from entrypoints.litestar.api.schemas import CamelCaseSchema

TelegramItemId = Annotated[
    str,
    PathParameter(
        description="Identifier of the authenticated user's Telegram invitation or connection.",
        examples=[Example(value="00000000000000000000000000000001")],
        schema_extra={"examples": ["00000000000000000000000000000001"]},
    ),
]


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
    notify_birthday: bool
    notify_memorable_date: bool
    notify_finance_transaction: bool
    notify_finance_limit: bool
    language: LanguageEnum

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
            notify_birthday=schema.notify_birthday,
            notify_memorable_date=schema.notify_memorable_date,
            notify_finance_transaction=schema.notify_finance_transaction,
            notify_finance_limit=schema.notify_finance_limit,
            language=schema.language,
        )


class TelegramConnectionSettingsRequest(CamelCaseSchema):
    notify_birthday: bool
    notify_memorable_date: bool
    notify_finance_transaction: bool
    notify_finance_limit: bool
    language: LanguageEnum

    def to_domain_schema(self) -> TelegramConnectionSettings:
        return TelegramConnectionSettings(
            notify_birthday=self.notify_birthday,
            notify_memorable_date=self.notify_memorable_date,
            notify_finance_transaction=self.notify_finance_transaction,
            notify_finance_limit=self.notify_finance_limit,
            language=self.language,
        )


class TelegramSettingsResponse(CamelCaseSchema):
    available: bool
    status: TelegramRuntimeStatus
    invitations: list[TelegramInvitationResponse]
    connections: list[TelegramConnectionResponse]


class TelegramRuntimeStatusResponse(CamelCaseSchema):
    status: TelegramRuntimeStatus


class TelegramIssuedInvitationResponse(CamelCaseSchema):
    url: str
    expires_at: datetime
