from typing import Annotated, Self

from pydantic import Field

from core.wiki_links.schemas import WikiLinkTargets
from entrypoints.litestar.api.schemas import CamelCaseSchema


class WikiLinkTargetsResponseSchema(CamelCaseSchema):
    targets: Annotated[tuple[()], Field(title="Targets")]

    @classmethod
    def from_domain_schema(cls, *, schema: WikiLinkTargets) -> Self:
        if schema.values:
            msg = "wiki-link target registry must remain empty"
            raise ValueError(msg)
        return cls(targets=())
