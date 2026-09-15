from typing import Any


class ApiFactoryHelper:
    @classmethod
    def hex_id(cls, value: int | str) -> str:
        if isinstance(value, str):
            return value
        return f"{value:032x}"

    @classmethod
    def resume_content(
        cls,
        full_name: str = "Candidate Name",
        role: str = "Инженер",
        summary: str = "Короткое описание опыта.",
        experience: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "profile": {
                "fullName": full_name,
                "role": role,
                "location": "",
                "email": "",
                "phone": "",
                "websiteUrl": "",
                "linkedinUrl": "",
                "githubUrl": "",
                "telegram": "",
            },
            "summary": {
                "text": summary,
            },
            "skills": [
                {
                    "category": "Backend",
                    "items": ["Python", "PostgreSQL"],
                },
            ],
            "experience": experience if experience is not None else [],
            "education": [],
            "languages": [],
            "certifications": [],
            "additionalSections": [],
        }

    @classmethod
    def resume_request(
        cls,
        title: str = "Backend resume",
        language: str = "ru",
        content: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "title": title,
            "language": language,
            "content": content if content is not None else cls.resume_content(),
        }
