from enum import Enum
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from core.i18n.enums import LanguageEnum


class BaseEnum(Enum):
    def __repr__(self) -> str:
        return self.__str__()

    def __str__(self) -> str:
        return str(self.value)

    @classmethod
    def from_value(cls, value: Any) -> Self:  # noqa: ANN401
        for member in cls:
            if member.value == value:
                return member
        msg = f"{value!r} is not a valid {cls.__name__}"
        raise ValueError(msg)


class StrEnum(str, BaseEnum):
    pass


class TranslationStrEnum(StrEnum):
    value_ru: str
    value_en: str

    def __new__(cls, value: str, value_ru: str, value_en: str) -> Self:
        member = str.__new__(cls, value)
        member._value_ = value
        member.value_ru = value_ru
        member.value_en = value_en
        return member

    def get_translation(self, language: LanguageEnum) -> str:
        return {"ru": self.value_ru, "en": self.value_en}[language.value]
