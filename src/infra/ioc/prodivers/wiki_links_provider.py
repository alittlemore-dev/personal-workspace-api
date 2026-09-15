from dishka import Provider, Scope, provide

from core.wiki_links.use_cases import WikiLinksUseCase


class WikiLinksProvider(Provider):
    @provide(scope=Scope.REQUEST)
    async def provide_wiki_links_use_case(self) -> WikiLinksUseCase:
        return WikiLinksUseCase()
