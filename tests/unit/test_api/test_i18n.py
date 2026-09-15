from httpx import codes

from tests.test_cases import ApiTestCase


class TestI18nApi(ApiTestCase):
    def test_lists_configured_languages(self) -> None:
        response = self.api.get_i18n_languages()

        self.asserts.status(response=response, expected_status=codes.OK)
        assert response.json() == {
            "defaultLanguage": "ru",
            "languages": [
                {"code": "ru", "label": "Русский"},
                {"code": "en", "label": "English"},
            ],
        }

    def test_returns_requested_language_bundle(self) -> None:
        response = self.api.get_i18n_bundle(language="en")

        self.asserts.status(response=response, expected_status=codes.OK)
        body = response.json()
        assert body["language"] == "en"
        assert body["messages"]["auth.login.title"] == "Sign in"
        assert body["messages"]["workspace.title"] == "Workspace"
        assert body["messages"]["enum.publishStatus.Draft"] == "Draft"

    def test_rejects_unknown_bundle_language(self) -> None:
        response = self.api.get_i18n_bundle(language="de")

        self.asserts.status(response=response, expected_status=codes.BAD_REQUEST)
