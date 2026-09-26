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
