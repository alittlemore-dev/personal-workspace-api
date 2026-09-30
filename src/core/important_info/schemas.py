from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class ImportantInfo:
    id: str
    text: str
    position: int


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateImportantInfoParams:
    text: str
    author_username: str


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateImportantInfoParams:
    item_id: str
    text: str
    author_username: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ImportantInfoTargetParams:
    item_id: str
    author_username: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SetImportantInfoOrderParams:
    ids: list[str]
    author_username: str
