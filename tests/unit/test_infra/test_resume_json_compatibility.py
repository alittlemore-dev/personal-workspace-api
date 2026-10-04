from dataclasses import replace

import pytest

from core.resumes.enums import ResumeDateFormatEnum
from core.resumes.schemas import ResumeSettings
from infra.postgresql.models.resumes import ResumeModel
from tests.test_cases import TestCase


class TestResumeJsonCompatibility(TestCase):
    def test_existing_resume_without_new_fields_remains_readable(self) -> None:
        resume = self.factory.core.resume(content=self.factory.core.resume_full_content())
        model = ResumeModel.from_domain_schema(resume=resume)
        model.content["profile"].pop("photo_file_id")
        experience = model.content["experience"][0]
        experience.pop("company_website_url")
        experience["projects"][0].pop("team_size")
        experience["projects"][0].pop("scale")

        loaded = model.to_domain_schema().content

        assert loaded.profile.photo_file_id == ""
        assert loaded.experience[0].company_website_url == ""
        assert loaded.experience[0].projects[0].team_size == ""
        assert loaded.experience[0].projects[0].scale == ""

    @pytest.mark.parametrize("date_format", list(ResumeDateFormatEnum))
    def test_required_settings_and_authored_blank_roles_round_trip(
        self,
        date_format: ResumeDateFormatEnum,
    ) -> None:
        content = self.factory.core.resume_full_content(date_format=date_format)
        experience = content.experience[0]
        content = replace(
            content,
            experience=[replace(experience, projects=[replace(experience.projects[0], role="")])],
        )
        model = ResumeModel.from_domain_schema(resume=self.factory.core.resume(content=content))
        assert model.content["settings"] == {
            "date_format": date_format.value,
            "section_order": [],
            "hidden_sections": [],
        }
        assert model.content["experience"][0]["projects"][0]["role"] == ""
        loaded = model.to_domain_schema().content
        assert loaded == content
        assert loaded.settings == ResumeSettings(
            date_format=date_format,
            section_order=[],
            hidden_sections=[],
        )
        assert (
            loaded.with_resolved_project_roles().experience[0].projects[0].role
            == experience.position
        )
        renamed = replace(
            loaded,
            experience=[replace(loaded.experience[0], position="Lead engineer")],
        )
        assert (
            renamed.with_resolved_project_roles().experience[0].projects[0].role == "Lead engineer"
        )
        assert renamed.experience[0].projects[0].role == ""
        assert experience.with_resolved_project_roles().projects[0].role == "Creator"

    def test_missing_settings_require_migration_instead_of_read_fallback(self) -> None:
        model = ResumeModel.from_domain_schema(resume=self.factory.core.resume())
        model.content.pop("settings")
        with pytest.raises(KeyError, match="settings"):
            model.to_domain_schema()

    @pytest.mark.parametrize("key", ["section_order", "hidden_sections"])
    def test_missing_section_settings_require_migration(self, key: str) -> None:
        model = ResumeModel.from_domain_schema(resume=self.factory.core.resume())
        model.content["settings"].pop(key)
        with pytest.raises(KeyError, match=key):
            model.to_domain_schema()
