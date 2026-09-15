from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from performance.query_plans.models import QueryPlanProfile
from performance.query_plans.scenarios import SEED_AUTHOR_USERNAME

SEEDED_TABLES = (
    "knowledge__knowledge_item_file_model",
    "files__file_model",
    "knowledge__date_person_model",
    "knowledge__person_relationship_model",
    "knowledge__date_details_model",
    "knowledge__person_details_model",
    "knowledge__person_relationship_type_model",
    "knowledge__knowledge_item_tag_model",
    "knowledge__knowledge_tag_model",
    "knowledge__knowledge_item_model",
    "resumes__resume_model",
)


def relationship_seed_keys(
    *,
    people: int,
    relationship_types: int,
    relationships: int,
) -> tuple[tuple[int, int, int], ...]:
    return tuple(
        relationship_seed_key(
            value=value,
            people=people,
            relationship_types=relationship_types,
        )
        for value in range(1, relationships + 1)
    )


def item_tag_seed_keys(*, items: int, tags: int, links: int) -> tuple[tuple[int, int], ...]:
    return tuple(
        (
            1 + ((value - 1) % items),
            1 + ((((value - 1) // items) + ((value - 1) % items)) % tags),
        )
        for value in range(1, links + 1)
    )


def date_person_seed_keys(*, dates: int, people: int, links: int) -> tuple[tuple[int, int], ...]:
    return tuple(
        (
            1 + ((value - 1) % dates),
            1 + ((((value - 1) // dates) + ((value - 1) % dates)) % people),
        )
        for value in range(1, links + 1)
    )


def relationship_seed_key(
    *, value: int, people: int, relationship_types: int
) -> tuple[int, int, int]:
    source_number = 1 + ((value - 1) % people)
    offset = 1 + ((value - 1) // people)
    target_number = 1 + ((source_number - 1 + offset) % people)
    return (
        min(source_number, target_number),
        max(source_number, target_number),
        1 + ((value - 1) % relationship_types),
    )


async def seed_profile(*, connection: AsyncConnection, profile: QueryPlanProfile) -> None:
    cardinalities = profile.cardinalities
    await clear_seeded_tables(connection=connection)
    await connection.execute(text("SET LOCAL synchronous_commit = off"))
    await connection.execute(
        text(
            """
            INSERT INTO resumes__resume_model
                (id, title, language, author_username, content, created_at, updated_at)
            SELECT
                md5('resume-' || value::text),
                'Benchmark resume ' || value::text,
                'EN'::language_enum,
                :author_username,
                '{"profile":{"full_name":"Query Plan","role":"Engineer","location":"",'
                '"email":"","phone":"","website_url":"","linkedin_url":"",'
                '"github_url":"","telegram":""},"summary":{"text":"seed"},"skills":[],'
                '"experience":[],"education":[],"languages":[],"certifications":[],'
                '"additional_sections":[]}'::jsonb,
                timezone('utc', current_timestamp) - value * interval '1 minute',
                timezone('utc', current_timestamp) - value * interval '1 minute'
            FROM generate_series(1, :resumes) AS series(value)
            """,
        ),
        {"author_username": SEED_AUTHOR_USERNAME, "resumes": cardinalities.resumes},
    )
    await connection.execute(
        text(
            """
            INSERT INTO knowledge__knowledge_item_model
                (id, kind, author_username, display_name, description, created_at, updated_at)
            SELECT
                md5('person-' || value::text),
                'PERSON'::knowledge_item_kind_enum,
                :author_username,
                CASE WHEN value % 10 = 0 THEN 'matched-person-' ELSE 'person-' END || value::text,
                'query-plan seed',
                timezone('utc', current_timestamp) - value * interval '1 minute',
                timezone('utc', current_timestamp) - value * interval '1 minute'
            FROM generate_series(1, :people) AS series(value)
            UNION ALL
            SELECT
                md5('date-' || value::text),
                'DATE'::knowledge_item_kind_enum,
                :author_username,
                CASE WHEN value % 10 = 0 THEN 'matched-date-' ELSE 'date-' END || value::text,
                'query-plan seed',
                timezone('utc', current_timestamp) - value * interval '1 minute',
                timezone('utc', current_timestamp) - value * interval '1 minute'
            FROM generate_series(1, :dates) AS series(value)
            """,
        ),
        {
            "author_username": SEED_AUTHOR_USERNAME,
            "people": cardinalities.people,
            "dates": cardinalities.dates,
        },
    )
    await connection.execute(
        text(
            """
            INSERT INTO knowledge__person_details_model (
                item_id, author_username, last_name, first_name, middle_name, email, phone,
                telegram, birthday_day, birthday_month, birthday_year
            )
            SELECT
                md5('person-' || value::text), :author_username,
                'Last' || value::text, 'First' || value::text, '',
                'person-' || value::text || '@example.test', '', '',
                1 + (value % 28), 1 + (value % 12), 2000
            FROM generate_series(1, :people) AS series(value)
            """,
        ),
        {"author_username": SEED_AUTHOR_USERNAME, "people": cardinalities.people},
    )
    await connection.execute(
        text(
            """
            INSERT INTO knowledge__date_details_model (item_id, author_username, day, month, year)
            SELECT
                md5('date-' || value::text), :author_username,
                1 + (value % 28), 1 + (value % 12), 2020
            FROM generate_series(1, :dates) AS series(value)
            """,
        ),
        {"author_username": SEED_AUTHOR_USERNAME, "dates": cardinalities.dates},
    )
    await connection.execute(
        text(
            """
            INSERT INTO knowledge__knowledge_tag_model
                (id, author_username, name, created_at, updated_at)
            SELECT md5('tag-' || value::text), :author_username,
                   'tag-' || lpad(value::text, 4, '0'),
                   timezone('utc', current_timestamp), timezone('utc', current_timestamp)
            FROM generate_series(1, :tags) AS series(value)
            """,
        ),
        {"author_username": SEED_AUTHOR_USERNAME, "tags": cardinalities.knowledge_tags},
    )
    await connection.execute(
        text(
            """
            INSERT INTO knowledge__knowledge_item_tag_model
                (item_id, tag_id, author_username, created_at, updated_at)
            SELECT
                CASE WHEN item_number <= :people THEN md5('person-' || item_number::text)
                     ELSE md5('date-' || (item_number - :people)::text) END,
                md5('tag-' || tag_number::text), :author_username,
                timezone('utc', current_timestamp), timezone('utc', current_timestamp)
            FROM (
                SELECT
                    1 + ((value - 1) % :items) AS item_number,
                    1 + (
                        ((value - 1) / :items)::integer + ((value - 1) % :items)
                    ) % :tags AS tag_number
                FROM generate_series(1, :links) AS series(value)
            ) AS links
            """,
        ),
        {
            "author_username": SEED_AUTHOR_USERNAME,
            "people": cardinalities.people,
            "items": cardinalities.knowledge_items,
            "tags": cardinalities.knowledge_tags,
            "links": cardinalities.knowledge_item_tag_links,
        },
    )
    await connection.execute(
        text(
            """
            INSERT INTO knowledge__person_relationship_type_model (
                id, author_username, is_symmetric, forward_name, reverse_name, created_at,
                updated_at
            )
            SELECT md5('relationship-type-' || value::text), :author_username, true,
                   'knows-' || value::text, 'knows-' || value::text,
                   timezone('utc', current_timestamp), timezone('utc', current_timestamp)
            FROM generate_series(1, :relationship_types) AS series(value)
            """,
        ),
        {
            "author_username": SEED_AUTHOR_USERNAME,
            "relationship_types": cardinalities.relationship_types,
        },
    )
    await connection.execute(
        text(
            """
            INSERT INTO knowledge__person_relationship_model (
                id, author_username, source_person_id, target_person_id, relationship_type_id,
                note, created_at, updated_at
            )
            SELECT
                md5('relationship-' || value::text), :author_username,
                md5('person-' || source_number::text),
                md5('person-' || target_number::text),
                md5('relationship-type-' || (1 + ((value - 1) % :relationship_types))::text),
                '', timezone('utc', current_timestamp), timezone('utc', current_timestamp)
            FROM (
                SELECT
                    value,
                    1 + ((value - 1) % :people) AS source_number,
                    1 + ((value - 1) / :people)::integer AS pair_offset
                FROM generate_series(1, :relationships) AS series(value)
            ) AS sources
            CROSS JOIN LATERAL (
                SELECT 1 + ((source_number - 1 + pair_offset) % :people) AS target_number
            ) AS targets
            """,
        ),
        {
            "author_username": SEED_AUTHOR_USERNAME,
            "people": cardinalities.people,
            "relationship_types": cardinalities.relationship_types,
            "relationships": cardinalities.relationships,
        },
    )
    await connection.execute(
        text(
            """
            INSERT INTO knowledge__date_person_model (date_item_id, person_item_id, author_username)
            SELECT
                md5('date-' || date_number::text),
                md5('person-' || person_number::text),
                :author_username
            FROM (
                SELECT
                    1 + ((value - 1) % :dates) AS date_number,
                    1 + (
                        ((value - 1) / :dates)::integer + ((value - 1) % :dates)
                    ) % :people AS person_number
                FROM generate_series(1, :date_person_links) AS series(value)
            ) AS links
            """,
        ),
        {
            "author_username": SEED_AUTHOR_USERNAME,
            "dates": cardinalities.dates,
            "people": cardinalities.people,
            "date_person_links": cardinalities.date_person_links,
        },
    )
    await connection.execute(
        text(
            """
            INSERT INTO files__file_model
                (id, purpose, namespace, relative_path, mime_type, size_bytes, name, original_name,
                 original_sha256, orphaned_at, created_at, updated_at)
            SELECT
                md5('file-' || value::text), 'ATTACHMENT'::file_purpose_enum,
                'knowledge-private', 'query-plan/' || value::text || '.bin',
                'application/octet-stream', value, 'file-' || value::text, 'file-' || value::text,
                NULL, NULL, timezone('utc', current_timestamp), timezone('utc', current_timestamp)
            FROM generate_series(1, :knowledge_files) AS series(value)
            """,
        ),
        {"knowledge_files": cardinalities.knowledge_files},
    )
    await connection.execute(
        text(
            """
            INSERT INTO knowledge__knowledge_item_file_model
                (file_id, item_id, author_username, kind, processing)
            SELECT
                md5('file-' || value::text),
                CASE WHEN item_number <= :people THEN md5('person-' || item_number::text)
                     ELSE md5('date-' || (item_number - :people)::text) END,
                :author_username,
                'ATTACHMENT'::knowledge_file_kind_enum, 'RAW'::knowledge_file_processing_enum
            FROM (
                SELECT value, 1 + ((value - 1) % :items) AS item_number
                FROM generate_series(1, :knowledge_files) AS series(value)
            ) AS files
            """,
        ),
        {
            "author_username": SEED_AUTHOR_USERNAME,
            "people": cardinalities.people,
            "items": cardinalities.knowledge_items,
            "knowledge_files": cardinalities.knowledge_files,
        },
    )


async def clear_seeded_tables(*, connection: AsyncConnection) -> None:
    await connection.execute(
        text(f"TRUNCATE TABLE {', '.join(SEEDED_TABLES)} RESTART IDENTITY CASCADE")
    )
