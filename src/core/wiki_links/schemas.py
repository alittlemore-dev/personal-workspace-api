from dataclasses import dataclass

from core.schemas import ValuedDataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class WikiLinkTargets(ValuedDataclass[object]): ...
