from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class ImportantInfo:
    id: str
    text: str
    position: int
