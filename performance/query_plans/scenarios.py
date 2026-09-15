from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from core.knowledge.dates.enums import KnowledgeDateListSort
from core.knowledge.dates.schemas import KnowledgeDateFilters
from core.knowledge.items.enums import KnowledgeItemKind
from core.knowledge.people.enums import PersonListSort
from core.knowledge.people.schemas import PersonFilters
from core.resumes.schemas import ResumeFilters
from infra.postgresql.storages.knowledge.dates import KnowledgeDatesDatabaseStorage
from infra.postgresql.storages.knowledge.files import KnowledgeFilesDatabaseStorage
from infra.postgresql.storages.knowledge.items import KnowledgeItemsDatabaseStorage
from infra.postgresql.storages.knowledge.people import PeopleDatabaseStorage
from infra.postgresql.storages.resumes import ResumesDatabaseStorage
from performance.query_plans.identifiers import seeded_identifier
from performance.query_plans.models import ExpectedIndex, PlanExpectation

SEED_AUTHOR_USERNAME = "query-plan-owner"
SEED_PERSON_ID = seeded_identifier(prefix="person", value=1)
SEED_DATE_ID = seeded_identifier(prefix="date", value=1)
SEED_TAG_ID = seeded_identifier(prefix="tag", value=1)


@dataclass(frozen=True, slots=True)
class StorageScenario:
    name: str
    storage_class: str
    method_name: str
    expectation: PlanExpectation
    run: Callable[[AsyncSession], Awaitable[None]]


async def run_resumes_list(session: AsyncSession) -> None:
    await ResumesDatabaseStorage(session=session).list_resumes(
        filters=ResumeFilters(
            page=1,
            page_size=20,
            search_query=None,
            author_username=SEED_AUTHOR_USERNAME,
        ),
    )


async def run_item_detail(session: AsyncSession) -> None:
    await KnowledgeItemsDatabaseStorage(session=session).get_item(
        item_id=SEED_PERSON_ID,
        author_username=SEED_AUTHOR_USERNAME,
        kind=KnowledgeItemKind.PERSON,
    )


async def run_tags_list(session: AsyncSession) -> None:
    await KnowledgeItemsDatabaseStorage(session=session).list_tags(
        author_username=SEED_AUTHOR_USERNAME,
        search_query="tag-01",
    )


async def run_dates_page(session: AsyncSession) -> None:
    await KnowledgeDatesDatabaseStorage(session=session).list_date_page(
        filters=KnowledgeDateFilters(
            page=1,
            page_size=20,
            sort=KnowledgeDateListSort.DATE_ASC,
            search_query="matched-date",
            tag_ids=(SEED_TAG_ID,),
            related_person_id=SEED_PERSON_ID,
            author_username=SEED_AUTHOR_USERNAME,
        ),
    )


async def run_date_backlinks(session: AsyncSession) -> None:
    await KnowledgeDatesDatabaseStorage(session=session).list_date_ids_for_person(
        person_id=SEED_PERSON_ID,
        author_username=SEED_AUTHOR_USERNAME,
    )


async def run_people_page(session: AsyncSession) -> None:
    await PeopleDatabaseStorage(session=session).list_person_page(
        filters=PersonFilters(
            page=1,
            page_size=20,
            sort=PersonListSort.NAME_ASC,
            search_query="matched-person",
            tag_ids=(SEED_TAG_ID,),
            author_username=SEED_AUTHOR_USERNAME,
        ),
    )


async def run_relationships(session: AsyncSession) -> None:
    await PeopleDatabaseStorage(session=session).list_relationships(
        person_id=SEED_PERSON_ID,
        author_username=SEED_AUTHOR_USERNAME,
    )


async def run_item_files(session: AsyncSession) -> None:
    await KnowledgeFilesDatabaseStorage(
        session=session,
        namespace="knowledge-private",
    ).list_files_for_items(
        item_ids={SEED_DATE_ID},
        author_username=SEED_AUTHOR_USERNAME,
    )


SCENARIOS = (
    StorageScenario(
        name="resumes_list",
        storage_class="ResumesDatabaseStorage",
        method_name="list_resumes",
        expectation=PlanExpectation(
            max_execution_ms=100.0,
            expected_indexes=(
                ExpectedIndex(
                    name="resumes_resume_author_updated_id_idx",
                    relation_name="resumes__resume_model",
                ),
            ),
            forbidden_seq_scan_relations=("resumes__resume_model",),
        ),
        run=run_resumes_list,
    ),
    StorageScenario(
        name="knowledge_item_detail",
        storage_class="KnowledgeItemsDatabaseStorage",
        method_name="get_item",
        expectation=PlanExpectation(
            max_execution_ms=100.0,
            expected_indexes=(
                ExpectedIndex(
                    name="knowledge_items_id_author_uniq",
                    relation_name="knowledge__knowledge_item_model",
                ),
            ),
            forbidden_seq_scan_relations=("knowledge__knowledge_item_model",),
        ),
        run=run_item_detail,
    ),
    StorageScenario(
        name="knowledge_tags_list",
        storage_class="KnowledgeItemsDatabaseStorage",
        method_name="list_tags",
        expectation=PlanExpectation(
            max_execution_ms=100.0,
            expected_indexes=(),
            forbidden_seq_scan_relations=(),
            allow_seq_scan_relations=("knowledge__knowledge_tag_model",),
        ),
        run=run_tags_list,
    ),
    StorageScenario(
        name="knowledge_dates_page",
        storage_class="KnowledgeDatesDatabaseStorage",
        method_name="list_date_page",
        expectation=PlanExpectation(
            max_execution_ms=250.0,
            expected_indexes=(
                ExpectedIndex(
                    name="knowledge_item_tags_author_tag_item_idx",
                    relation_name="knowledge__knowledge_item_tag_model",
                ),
            ),
            forbidden_seq_scan_relations=(
                "knowledge__date_person_model",
                "knowledge__knowledge_item_tag_model",
            ),
        ),
        run=run_dates_page,
    ),
    StorageScenario(
        name="knowledge_date_backlinks",
        storage_class="KnowledgeDatesDatabaseStorage",
        method_name="list_date_ids_for_person",
        expectation=PlanExpectation(
            max_execution_ms=100.0,
            expected_indexes=(
                ExpectedIndex(
                    name="date_people_author_person_date_idx",
                    relation_name="knowledge__date_person_model",
                ),
            ),
            forbidden_seq_scan_relations=("knowledge__date_person_model",),
        ),
        run=run_date_backlinks,
    ),
    StorageScenario(
        name="people_page",
        storage_class="PeopleDatabaseStorage",
        method_name="list_person_page",
        expectation=PlanExpectation(
            max_execution_ms=250.0,
            expected_indexes=(
                ExpectedIndex(
                    name="knowledge_item_tags_author_tag_item_idx",
                    relation_name="knowledge__knowledge_item_tag_model",
                ),
            ),
            forbidden_seq_scan_relations=("knowledge__knowledge_item_tag_model",),
        ),
        run=run_people_page,
    ),
    StorageScenario(
        name="people_relationships",
        storage_class="PeopleDatabaseStorage",
        method_name="list_relationships",
        expectation=PlanExpectation(
            max_execution_ms=100.0,
            expected_indexes=(
                ExpectedIndex(
                    name="person_relationships_author_source_idx",
                    relation_name="knowledge__person_relationship_model",
                ),
            ),
            forbidden_seq_scan_relations=("knowledge__person_relationship_model",),
        ),
        run=run_relationships,
    ),
    StorageScenario(
        name="knowledge_item_files",
        storage_class="KnowledgeFilesDatabaseStorage",
        method_name="list_files_for_items",
        expectation=PlanExpectation(
            max_execution_ms=100.0,
            expected_indexes=(
                ExpectedIndex(
                    name="knowledge_item_files_author_item_kind_file_idx",
                    relation_name="knowledge__knowledge_item_file_model",
                ),
            ),
            forbidden_seq_scan_relations=("knowledge__knowledge_item_file_model",),
        ),
        run=run_item_files,
    ),
)
