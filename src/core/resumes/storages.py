from abc import ABC, abstractmethod

from core.resumes.schemas import Resume, ResumeCreateParams, ResumeFilters


class ResumesStorage(ABC):
    @abstractmethod
    async def list_resumes(self, *, filters: ResumeFilters) -> tuple[list[Resume], int]:
        raise NotImplementedError

    @abstractmethod
    async def get_resume(self, *, resume_id: str, author_username: str) -> Resume:
        raise NotImplementedError

    @abstractmethod
    async def create_resume(self, *, params: ResumeCreateParams) -> Resume:
        raise NotImplementedError

    @abstractmethod
    async def update_resume(self, *, resume: Resume) -> Resume:
        raise NotImplementedError

    @abstractmethod
    async def delete_resume(self, *, resume_id: str, author_username: str) -> None:
        raise NotImplementedError
