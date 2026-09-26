from enum import IntEnum


class ResumeLimits(IntEnum):
    phone_min_digits = 7
    phone_max_digits = 20
    skill_groups = 12
    skills_per_group = 30
    skills_total = 200
    experience = 20
    projects_per_experience = 15
    projects_total = 100
    experience_highlights = 15
    project_highlights = 12
    experience_technologies = 30
    project_technologies = 50
    education = 8
    languages = 9
    certifications = 15
    additional_sections = 6
    additional_items_per_section = 12
    additional_items_total = 30
    visible_text = 50_000
    summary = 1_200
    experience_summary = 800
    project_description = 600
    education_description = 500
    additional_description = 500
    highlight = 512
