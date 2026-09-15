import pytest

from performance.query_plans import models as query_plan_models
from performance.query_plans.runner import get_profile
from performance.query_plans.seed import (
    date_person_seed_keys,
    item_tag_seed_keys,
    relationship_seed_keys,
)


class TestQueryPlanProfiles:
    def test_realistic_profile_models_current_knowledge_and_resumes_relations(self) -> None:
        profile = get_profile(name="realistic")

        assert profile is query_plan_models.REALISTIC_PROFILE
        assert profile.cardinalities == query_plan_models.ProfileCardinalities(
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
        )
        assert profile.relation_cardinalities == {
            "resumes__resume_model": 250,
            "knowledge__knowledge_item_model": 5_000,
            "knowledge__knowledge_tag_model": 500,
            "knowledge__knowledge_item_tag_model": 20_000,
            "knowledge__person_details_model": 2_500,
            "knowledge__date_details_model": 2_500,
            "knowledge__date_person_model": 10_000,
            "knowledge__person_relationship_type_model": 100,
            "knowledge__person_relationship_model": 10_000,
            "knowledge__knowledge_item_file_model": 5_000,
            "files__file_model": 5_000,
        }

    def test_unknown_profile_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unknown query plan profile: stress"):
            get_profile(name="stress")

    def test_realistic_relationship_seed_keys_are_unique_for_normalized_pair_constraint(
        self,
    ) -> None:
        cardinalities = query_plan_models.REALISTIC_PROFILE.cardinalities

        keys = tuple(
            relationship_seed_keys(
                people=cardinalities.people,
                relationship_types=cardinalities.relationship_types,
                relationships=cardinalities.relationships,
            ),
        )

        assert len(keys) == cardinalities.relationships
        assert len(set(keys)) == cardinalities.relationships

    def test_realistic_item_tag_seed_uses_declared_tag_cardinality(self) -> None:
        cardinalities = query_plan_models.REALISTIC_PROFILE.cardinalities

        keys = item_tag_seed_keys(
            items=cardinalities.knowledge_items,
            tags=cardinalities.knowledge_tags,
            links=cardinalities.knowledge_item_tag_links,
        )

        assert len(keys) == cardinalities.knowledge_item_tag_links
        assert len(set(keys)) == cardinalities.knowledge_item_tag_links
        assert {tag_number for _, tag_number in keys} == set(
            range(1, cardinalities.knowledge_tags + 1),
        )
        assert (1, 1) in keys

    def test_realistic_date_person_seed_uses_declared_people_cardinality(self) -> None:
        cardinalities = query_plan_models.REALISTIC_PROFILE.cardinalities

        keys = date_person_seed_keys(
            dates=cardinalities.dates,
            people=cardinalities.people,
            links=cardinalities.date_person_links,
        )

        assert len(keys) == cardinalities.date_person_links
        assert len(set(keys)) == cardinalities.date_person_links
        assert {person_number for _, person_number in keys} == set(
            range(1, cardinalities.people + 1),
        )
        assert (1, 1) in keys
