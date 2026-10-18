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
    label: Annotated[
        str,
        Field(
            min_length=1,
            max_length=100,
            description="User-defined label for this invitation or connection.",
            examples=["Family notifications"],
        ),
    ]

    @field_validator("label")
    @classmethod
    def strip_nonblank_label(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            message = "Label must not be blank"
            raise ValueError(message)
        return stripped


class TelegramInvitationResponse(CamelCaseSchema):
    id: str = Field(
        description="Opaque resource identifier; use the value returned by this API.",
        examples=["4e92d4de561f4bc7a3eed227868952db"],
    )
    label: str = Field(
        description="User-defined label for this invitation or connection.",
        examples=["Family notifications"],
    )
    expires_at: datetime = Field(
        description="Expiration timestamp in ISO 8601 format.",
        examples=["2026-10-19T09:00:00Z"],
    )

    @classmethod
    def from_domain_schema(cls, schema: TelegramInvitation) -> TelegramInvitationResponse:
        return cls(id=schema.id, label=schema.label, expires_at=schema.expires_at)


class TelegramConnectionResponse(CamelCaseSchema):
    id: str = Field(
        description="Opaque resource identifier; use the value returned by this API.",
        examples=["4e92d4de561f4bc7a3eed227868952db"],
    )
    label: str = Field(
        description="User-defined label for this invitation or connection.",
        examples=["Family notifications"],
    )
    telegram_user_id: int = Field(description="Telegram user identifier.", examples=[123456789])
    username: str = Field(
        description="Telegram username, without the @ prefix.",
        examples=["alex_morgan"],
    )
    first_name: str = Field(description="Given name.", examples=["Alex"])
    state: str = Field(
        description="Connection lifecycle state: pending, active, revoked, or blocked.",
        examples=["active"],
    )
    requested_at: datetime = Field(
        description="Time the Telegram connection was requested.",
        examples=["2026-10-18T09:00:00Z"],
    )
    connected_at: datetime | None = Field(
        description="Time the connection was approved; null until approved.",
        examples=["2026-10-18T09:05:00Z"],
    )
    last_contact_at: datetime = Field(
        description="Last contact received from this Telegram connection.",
        examples=["2026-10-18T10:00:00Z"],
    )
    notify_birthday: bool = Field(
        description="Receive birthday notifications through this connection.",
        examples=[True],
    )
    notify_memorable_date: bool = Field(
        description="Receive memorable date notifications through this connection.",
        examples=[True],
    )
    notify_finance_transaction: bool = Field(
        description="Receive notifications about finance transactions.",
        examples=[True],
    )
    notify_finance_limit: bool = Field(
        description="Receive notifications when finance spending limits are exceeded.",
        examples=[True],
    )
    language: LanguageEnum = Field(
        description="Language; allowed values are listed in the referenced enumeration.",
        examples=["en"],
    )

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
    notify_birthday: bool = Field(
        description="Receive birthday notifications through this connection.",
        examples=[True],
    )
    notify_memorable_date: bool = Field(
        description="Receive memorable date notifications through this connection.",
        examples=[True],
    )
    notify_finance_transaction: bool = Field(
        description="Receive notifications about finance transactions.",
        examples=[True],
    )
    notify_finance_limit: bool = Field(
        description="Receive notifications when finance spending limits are exceeded.",
        examples=[True],
    )
    language: LanguageEnum = Field(
        description="Language; allowed values are listed in the referenced enumeration.",
        examples=["en"],
    )

    def to_domain_schema(self) -> TelegramConnectionSettings:
        return TelegramConnectionSettings(
            notify_birthday=self.notify_birthday,
            notify_memorable_date=self.notify_memorable_date,
            notify_finance_transaction=self.notify_finance_transaction,
            notify_finance_limit=self.notify_finance_limit,
            language=self.language,
        )


class TelegramSettingsResponse(CamelCaseSchema):
    available: bool = Field(
        description="Whether the Telegram service can currently accept management operations.",
        examples=[True],
    )
    status: TelegramRuntimeStatus = Field(
        description="Status; allowed values are listed in the referenced enumeration.",
        examples=["ready"],
    )
    invitations: list[TelegramInvitationResponse] = Field(
        description="Invitations returned by this operation.",
    )
    connections: list[TelegramConnectionResponse] = Field(
        description="Connections returned by this operation.",
    )


class TelegramRuntimeStatusResponse(CamelCaseSchema):
    status: TelegramRuntimeStatus = Field(
        description="Status; allowed values are listed in the referenced enumeration.",
        examples=["ready"],
    )


class TelegramIssuedInvitationResponse(CamelCaseSchema):
    url: str = Field(
        description="Telegram bot deep link. Treat the invitation token as a secret.",
        examples=["https://t.me/example_bot?start=example-invitation-token"],
    )
    expires_at: datetime = Field(
        description="Expiration timestamp in ISO 8601 format.",
        examples=["2026-10-19T09:00:00Z"],
    )
