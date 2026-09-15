from abc import ABC, abstractmethod

from core.knowledge.dates.schemas import (
    KnowledgeDateDetails,
    KnowledgeDateFilters,
    KnowledgeDatePersonLink,
)


class KnowledgeDatesStorage(ABC):
    @abstractmethod
    async def list_details_for_months(
        self,
        *,
        months: tuple[int, ...],
        author_username: str,
    ) -> list[KnowledgeDateDetails]:
        raise NotImplementedError

    @abstractmethod
    async def list_date_page(
        self,
        *,
        filters: KnowledgeDateFilters,
    ) -> tuple[list[str], int]:
        raise NotImplementedError

    @abstractmethod
    async def list_details(
        self,
        *,
        item_ids: list[str],
        author_username: str,
    ) -> list[KnowledgeDateDetails]:
        raise NotImplementedError

    @abstractmethod
    async def get_details(
        self,
        *,
        item_id: str,
        author_username: str,
    ) -> KnowledgeDateDetails:
        raise NotImplementedError

    @abstractmethod
    async def create_details(
        self,
        *,
        details: KnowledgeDateDetails,
        author_username: str,
    ) -> KnowledgeDateDetails:
        raise NotImplementedError

    @abstractmethod
    async def update_details(
        self,
        *,
        details: KnowledgeDateDetails,
        author_username: str,
    ) -> KnowledgeDateDetails:
        raise NotImplementedError

    @abstractmethod
    async def list_person_links(
        self,
        *,
        date_ids: set[str],
        author_username: str,
    ) -> list[KnowledgeDatePersonLink]:
        raise NotImplementedError

    @abstractmethod
    async def list_date_ids_for_person(
        self,
        *,
        person_id: str,
        author_username: str,
    ) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    async def replace_person_links(
        self,
        *,
        date_id: str,
        person_ids: list[str],
        author_username: str,
    ) -> None:
        raise NotImplementedError
