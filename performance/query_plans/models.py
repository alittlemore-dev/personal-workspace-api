from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProfileCardinalities:
    resumes: int
    knowledge_items: int
    knowledge_tags: int
    knowledge_item_tag_links: int
    people: int
    dates: int
    date_person_links: int
    relationship_types: int
    relationships: int
    knowledge_files: int


@dataclass(frozen=True, slots=True)
class QueryPlanProfile:
    name: str
    cardinalities: ProfileCardinalities

    @property
    def relation_cardinalities(self) -> Mapping[str, int]:
        cardinalities = self.cardinalities
        return {
            "resumes__resume_model": cardinalities.resumes,
            "knowledge__knowledge_item_model": cardinalities.knowledge_items,
            "knowledge__knowledge_tag_model": cardinalities.knowledge_tags,
            "knowledge__knowledge_item_tag_model": cardinalities.knowledge_item_tag_links,
            "knowledge__person_details_model": cardinalities.people,
            "knowledge__date_details_model": cardinalities.dates,
            "knowledge__date_person_model": cardinalities.date_person_links,
            "knowledge__person_relationship_type_model": cardinalities.relationship_types,
            "knowledge__person_relationship_model": cardinalities.relationships,
            "knowledge__knowledge_item_file_model": cardinalities.knowledge_files,
            "files__file_model": cardinalities.knowledge_files,
        }


@dataclass(frozen=True, slots=True)
class ExpectedIndex:
    name: str
    relation_name: str


@dataclass(frozen=True, slots=True)
class PlanExpectation:
    max_execution_ms: float
    expected_indexes: tuple[ExpectedIndex, ...]
    forbidden_seq_scan_relations: tuple[str, ...]
    allow_seq_scan_relations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PlanAnalysis:
    name: str
    execution_time_ms: float
    index_names: tuple[str, ...]
    seq_scan_relations: tuple[str, ...]
    blocking_findings: tuple[str, ...]
    observations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CapturedQuery:
    name: str
    scenario_name: str
    storage_class: str
    method_name: str
    sql: str
    parameters: object
    expectation: PlanExpectation


REALISTIC_PROFILE = QueryPlanProfile(
    name="realistic",
    cardinalities=ProfileCardinalities(
        resumes=250,
        knowledge_items=5_000,
        knowledge_tags=500,
        knowledge_item_tag_links=20_000,
        people=2_500,
        dates=2_500,
        date_person_links=10_000,
        relationship_types=100,
        relationships=10_000,
        knowledge_files=5_000,
    ),
)
