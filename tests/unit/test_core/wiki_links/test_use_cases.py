from core.i18n.enums import LanguageEnum
from core.wiki_links.schemas import WikiLinkTargets
from core.wiki_links.use_cases import WikiLinksUseCase
from tests.test_cases import TestCase


class TestWikiLinksUseCase(TestCase):
    async def test_list_targets_returns_empty_targets_until_new_sources_are_implemented(
        self,
    ) -> None:
        use_case = WikiLinksUseCase()

        result = await use_case.list_targets(language=LanguageEnum.EN)

        assert result == WikiLinkTargets(values=[])
