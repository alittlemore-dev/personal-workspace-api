from dataclasses import dataclass
from datetime import datetime

from core.resumes.exporters import ResumeDocumentExporter
from core.resumes.schemas import (
    Resume,
    ResumeCreateParams,
    ResumeExport,
    ResumeExportParams,
    ResumeFilters,
    Resumes,
    ResumeUpdateParams,
)
from core.resumes.storages import ResumesStorage


@dataclass(kw_only=True, slots=True, frozen=True)
class ResumesUseCase:
    storage: ResumesStorage
    exporter: ResumeDocumentExporter

    async def list_resumes(self, *, filters: ResumeFilters) -> Resumes:
        if filters.page is None or filters.page_size is None:
            message = "pagination required"
            raise ValueError(message)
        resumes, total_count = await self.storage.list_resumes(filters=filters)
        return Resumes.from_page(
            values=resumes,
            total_count=total_count,
            page_size=filters.page_size,
        )

    async def get_resume(self, *, resume_id: str, author_username: str) -> Resume:
        return await self.storage.get_resume(
            resume_id=resume_id,
            author_username=author_username,
        )

    async def create_resume(self, *, params: ResumeCreateParams) -> Resume:
        return await self.storage.create_resume(params=params)

    async def update_resume(
        self,
        *,
        resume_id: str,
        params: ResumeUpdateParams,
        author_username: str,
        current_datetime: datetime,
    ) -> Resume:
        existing_resume = await self.storage.get_resume(
            resume_id=resume_id,
            author_username=author_username,
        )
        return await self.storage.update_resume(
            resume=params.to_resume(existing_resume=existing_resume, now=current_datetime),
        )

    async def delete_resume(self, *, resume_id: str, author_username: str) -> None:
        await self.storage.delete_resume(resume_id=resume_id, author_username=author_username)

    async def export_resume(
        self,
        *,
        resume_id: str,
        params: ResumeExportParams,
        author_username: str,
    ) -> ResumeExport:
        await self.storage.get_resume(
            resume_id=resume_id,
            author_username=author_username,
        )
        return self.exporter.export_resume(params=params)
