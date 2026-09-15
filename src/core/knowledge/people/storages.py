from abc import ABC, abstractmethod
from datetime import datetime

from core.knowledge.people.schemas import (
    PersonDetails,
    PersonFilters,
    PersonRelationship,
    PersonRelationshipCreateParams,
    PersonRelationshipType,
    PersonRelationshipTypeCreateParams,
    PersonRelationshipTypeUpdateParams,
    PersonRelationshipUpdateParams,
)


class PeopleStorage(ABC):
    @abstractmethod
    async def list_birthday_details_for_months(
        self,
        *,
        months: tuple[int, ...],
        author_username: str,
    ) -> list[PersonDetails]:
        raise NotImplementedError

    @abstractmethod
    async def list_person_page(
        self,
        *,
        filters: PersonFilters,
    ) -> tuple[list[str], int]:
        raise NotImplementedError

    @abstractmethod
    async def list_details(
        self,
        *,
        item_ids: list[str],
        author_username: str,
    ) -> list[PersonDetails]:
        raise NotImplementedError

    @abstractmethod
    async def get_details(self, *, item_id: str, author_username: str) -> PersonDetails:
        raise NotImplementedError

    @abstractmethod
    async def create_details(
        self,
        *,
        details: PersonDetails,
        author_username: str,
    ) -> PersonDetails:
        raise NotImplementedError

    @abstractmethod
    async def update_details(
        self,
        *,
        details: PersonDetails,
        author_username: str,
    ) -> PersonDetails:
        raise NotImplementedError

    @abstractmethod
    async def list_relationships(
        self,
        *,
        person_id: str,
        author_username: str,
    ) -> list[PersonRelationship]:
        raise NotImplementedError

    @abstractmethod
    async def get_relationships_by_ids(
        self,
        *,
        relationship_ids: set[str],
        author_username: str,
    ) -> list[PersonRelationship]:
        raise NotImplementedError

    @abstractmethod
    async def list_related_person_ids(
        self,
        *,
        person_id: str,
        author_username: str,
    ) -> set[str]:
        raise NotImplementedError

    @abstractmethod
    async def create_relationships(
        self,
        *,
        person_id: str,
        author_username: str,
        values: list[PersonRelationshipCreateParams],
        relationship_types: dict[str, PersonRelationshipType],
        created_at: datetime,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def update_relationships(
        self,
        *,
        person_id: str,
        author_username: str,
        values: list[PersonRelationshipUpdateParams],
        relationship_types: dict[str, PersonRelationshipType],
        updated_at: datetime,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_relationships(
        self,
        *,
        relationship_ids: set[str],
        author_username: str,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_relationship_types(
        self,
        *,
        author_username: str,
    ) -> list[PersonRelationshipType]:
        raise NotImplementedError

    @abstractmethod
    async def get_relationship_type(
        self,
        *,
        relationship_type_id: str,
        author_username: str,
    ) -> PersonRelationshipType:
        raise NotImplementedError

    @abstractmethod
    async def get_relationship_types_by_ids(
        self,
        *,
        relationship_type_ids: set[str],
        author_username: str,
    ) -> list[PersonRelationshipType]:
        raise NotImplementedError

    @abstractmethod
    async def create_relationship_type(
        self,
        *,
        params: PersonRelationshipTypeCreateParams,
    ) -> PersonRelationshipType:
        raise NotImplementedError

    @abstractmethod
    async def update_relationship_type(
        self,
        *,
        relationship_type: PersonRelationshipType,
        params: PersonRelationshipTypeUpdateParams,
        updated_at: datetime,
    ) -> PersonRelationshipType:
        raise NotImplementedError

    @abstractmethod
    async def is_relationship_type_used(
        self,
        *,
        relationship_type_id: str,
        author_username: str,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def delete_relationship_type(
        self,
        *,
        relationship_type_id: str,
        author_username: str,
    ) -> None:
        raise NotImplementedError
