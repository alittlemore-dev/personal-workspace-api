import pytest
import pytest_asyncio
from httpx import codes
from pydantic import ValidationError

from core.i18n.enums import LanguageEnum
from core.wiki_links.schemas import WikiLinkTargets
from entrypoints.litestar.api.wiki_links.schemas import WikiLinkTargetsResponseSchema
from tests.test_cases import ApiTestCase


class TestWikiLinkTargetsApi(ApiTestCase):
    @pytest_asyncio.fixture(autouse=True)
    async def setup(self) -> None:
        self.use_case = await self.container.get_wiki_links_use_case()

    def test_maps_current_empty_registry_and_requested_language(self) -> None:
        self.use_case.list_targets.return_value = WikiLinkTargets(values=[])

        response = self.api.get_wiki_link_targets(language="en")

        self.asserts.status(response=response, expected_status=codes.OK)
        assert response.json() == {"targets": []}
        self.use_case.list_targets.assert_awaited_once_with(language=LanguageEnum.EN)

    def test_requires_explicit_language(self) -> None:
        response = self.api.get_wiki_link_targets(language=None)

        self.asserts.status(response=response, expected_status=codes.BAD_REQUEST)
        self.use_case.list_targets.assert_not_called()

    def test_response_contract_rejects_removed_target_domains(self) -> None:
        with pytest.raises(ValidationError):
            WikiLinkTargetsResponseSchema.model_validate(
                {
                    "targets": [
                        {
                            "type": "articles",
                            "items": [],
                        },
                    ],
                },
            )
