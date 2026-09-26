from dataclasses import dataclass, replace
from datetime import datetime

from core.files.exceptions import FilePurposeNotAllowedError
from core.files.schemas import FileUploadParams
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
from core.resumes.services import ResumePhotoFileService
from core.resumes.storages import ResumesStorage


@dataclass(kw_only=True, slots=True, frozen=True)
class ResumesUseCase:
    storage: ResumesStorage
    exporter: ResumeDocumentExporter
    photo_files: ResumePhotoFileService

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
        if params.content.profile.photo_file_id:
            raise FilePurposeNotAllowedError
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
        old_photo_id = existing_resume.content.profile.photo_file_id
        new_photo_id = params.content.profile.photo_file_id
        if new_photo_id and new_photo_id != old_photo_id:
            raise FilePurposeNotAllowedError
        updated = await self.storage.update_resume(
            resume=params.to_resume(existing_resume=existing_resume, now=current_datetime),
        )
        if old_photo_id and not new_photo_id:
            await self.photo_files.sync_file_usages(
                attached_file_ids=frozenset(),
                detached_file_ids=frozenset({old_photo_id}),
                orphaned_at=current_datetime,
            )
        return updated

    async def upload_photo(
        self,
        *,
        resume_id: str,
        author_username: str,
        params: FileUploadParams,
        current_datetime: datetime,
    ) -> Resume:
        existing = await self.storage.get_resume(
            resume_id=resume_id,
            author_username=author_username,
        )
        uploaded = await self.photo_files.upload_file(
            params=params,
            current_datetime=current_datetime,
        )
        old_id = existing.content.profile.photo_file_id
        updated = await self.storage.update_resume(
            resume=replace(
                existing,
                content=replace(
                    existing.content,
                    profile=replace(existing.content.profile, photo_file_id=uploaded.file.id),
                ),
                updated_at=current_datetime,
            ),
        )
        await self.photo_files.sync_file_usages(
            attached_file_ids=frozenset({uploaded.file.id}),
            detached_file_ids=frozenset({old_id})
            if old_id and old_id != uploaded.file.id
            else frozenset(),
            orphaned_at=current_datetime,
        )
        return updated

    async def read_photo(self, *, resume_id: str, author_username: str) -> bytes:
        resume = await self.storage.get_resume(resume_id=resume_id, author_username=author_username)
        file_id = resume.content.profile.photo_file_id
        if not file_id:
            raise FilePurposeNotAllowedError
        await self.photo_files.ensure_photo_file_allowed(file_id=file_id)
        return await self.photo_files.download_file(file_id=file_id)

    async def delete_resume(
        self,
        *,
        resume_id: str,
        author_username: str,
        current_datetime: datetime,
    ) -> None:
        existing = await self.storage.get_resume(
            resume_id=resume_id,
            author_username=author_username,
        )
        await self.storage.delete_resume(resume_id=resume_id, author_username=author_username)
        file_id = existing.content.profile.photo_file_id
        if file_id:
            await self.photo_files.sync_file_usages(
                attached_file_ids=frozenset(),
                detached_file_ids=frozenset({file_id}),
                orphaned_at=current_datetime,
            )

    async def export_resume(
        self,
        *,
        resume_id: str,
        params: ResumeExportParams,
        author_username: str,
    ) -> ResumeExport:
        existing = await self.storage.get_resume(
            resume_id=resume_id,
            author_username=author_username,
        )
        file_id = params.content.profile.photo_file_id
        if file_id and file_id != existing.content.profile.photo_file_id:
            raise FilePurposeNotAllowedError
        photo_content = (
            await self.read_photo(resume_id=resume_id, author_username=author_username)
            if file_id
            else b""
        )
        return self.exporter.export_resume(params=params, photo_content=photo_content)
