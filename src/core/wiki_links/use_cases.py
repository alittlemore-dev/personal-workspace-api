from core.i18n.enums import LanguageEnum
from core.wiki_links.schemas import WikiLinkTargets


class WikiLinksUseCase:
    async def list_targets(self, *, language: LanguageEnum) -> WikiLinkTargets:
        del language
        return WikiLinkTargets(values=[])
