from typing import Annotated

from pydantic import AfterValidator, EmailStr, Field, HttpUrl, TypeAdapter, ValidationError

from infra.config.constants import constants


def trim_required(value: str) -> str:
    trimmed_value = value.strip()
    if not trimmed_value:
        msg = "value must not be blank"
        raise ValueError(msg)
    return trimmed_value


def validate_required_http_url(value: str) -> str:
    trimmed_value = trim_required(value)
    validate_http_url_format(trimmed_value)
    return trimmed_value


def validate_optional_http_url(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed_value = value.strip()
    if not trimmed_value:
        return None
    validate_http_url_format(trimmed_value)
    return trimmed_value


def validate_blankable_http_url(value: str) -> str:
    trimmed_value = value.strip()
    if not trimmed_value:
        return ""
    validate_http_url_format(trimmed_value)
    return trimmed_value


def validate_blankable_email(value: str) -> str:
    trimmed_value = value.strip()
    if not trimmed_value:
        return ""
    try:
        _email_adapter.validate_python(trimmed_value)
    except ValidationError as error:
        msg = "value must be a valid email address"
        raise ValueError(msg) from error
    return trimmed_value


def validate_optional_email(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed_value = value.strip()
    if not trimmed_value:
        msg = "value must not be blank"
        raise ValueError(msg)
    try:
        _email_adapter.validate_python(trimmed_value)
    except ValidationError as error:
        msg = "value must be a valid email address"
        raise ValueError(msg) from error
    return trimmed_value


def validate_http_url_format(value: str) -> None:
    try:
        _http_url_adapter.validate_python(value)
    except ValidationError as error:
        msg = "value must be a valid http or https URL"
        raise ValueError(msg) from error


_http_url_adapter = TypeAdapter(HttpUrl)
_email_adapter = TypeAdapter(EmailStr)

RequiredShortText = Annotated[
    str,
    Field(
        min_length=1,
        max_length=constants.api_validation.short_text_max_length,
    ),
    AfterValidator(trim_required),
]
RequiredHttpUrlString = Annotated[
    str,
    Field(
        min_length=1,
        max_length=constants.api_validation.url_max_length,
    ),
    AfterValidator(validate_required_http_url),
]
OptionalHttpUrlString = Annotated[
    str | None,
    Field(max_length=constants.api_validation.url_max_length),
    AfterValidator(validate_optional_http_url),
]
BlankableHttpUrlString = Annotated[
    str,
    Field(max_length=constants.api_validation.url_max_length),
    AfterValidator(validate_blankable_http_url),
]
BlankableEmailString = Annotated[
    str,
    Field(max_length=constants.api_validation.email_max_length),
    AfterValidator(validate_blankable_email),
]
OptionalEmailString = Annotated[
    str | None,
    Field(
        min_length=1,
        max_length=constants.api_validation.email_max_length,
    ),
    AfterValidator(validate_optional_email),
]
ResumeLongText = Annotated[
    str,
    Field(max_length=constants.api_validation.resume_long_text_max_length),
]
KnowledgeDescriptionText = Annotated[
    str,
    Field(max_length=constants.api_validation.knowledge_description_max_length),
]
KnowledgeRelationshipNoteText = Annotated[
    str,
    Field(max_length=constants.api_validation.knowledge_relationship_note_max_length),
]
ShortText = Annotated[
    str,
    Field(max_length=constants.api_validation.short_text_max_length),
]
