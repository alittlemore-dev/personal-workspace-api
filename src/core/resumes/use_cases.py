from dataclasses import dataclass, replace

from core.files.exceptions import FilePurposeNotAllowedError
from core.resumes.exporters import ResumeDocumentExporter
from core.resumes.schemas import (
    DeleteResumeParams,
    ExportResumeParams,
    Resume,
    ResumeCreateParams,
    ResumeExport,
    ResumeFilters,
    Resumes,
    ResumeTargetParams,
    UpdateResumeParams,
    UploadResumePhotoParams,
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

    async def get_resume(self, *, params: ResumeTargetParams) -> Resume:
        return await self.storage.get_resume(
            resume_id=params.resume_id,
            author_username=params.author_username,
        )

    async def create_resume(self, *, params: ResumeCreateParams) -> Resume:
        if params.content.profile.photo_file_id:
            raise FilePurposeNotAllowedError
        return await self.storage.create_resume(params=params)

    async def update_resume(self, *, params: UpdateResumeParams) -> Resume:
        existing_resume = await self.storage.get_resume(
            resume_id=params.resume_id,
            author_username=params.author_username,
        )
        old_photo_id = existing_resume.content.profile.photo_file_id
        new_photo_id = params.data.content.profile.photo_file_id
        if new_photo_id and new_photo_id != old_photo_id:
            raise FilePurposeNotAllowedError
        updated = await self.storage.update_resume(
            resume=params.data.to_resume(
                existing_resume=existing_resume,
                now=params.current_datetime,
            ),
        )
        if old_photo_id and not new_photo_id:
            await self.photo_files.sync_file_usages(
                attached_file_ids=frozenset(),
                detached_file_ids=frozenset({old_photo_id}),
                orphaned_at=params.current_datetime,
            )
        return updated

    async def upload_photo(self, *, params: UploadResumePhotoParams) -> Resume:
        existing = await self.storage.get_resume(
            resume_id=params.resume_id,
            author_username=params.author_username,
        )
        uploaded = await self.photo_files.upload_file(
            params=params.data,
            current_datetime=params.current_datetime,
        )
        old_id = existing.content.profile.photo_file_id
        updated = await self.storage.update_resume(
            resume=replace(
                existing,
                content=replace(
                    existing.content,
                    profile=replace(existing.content.profile, photo_file_id=uploaded.file.id),
                ),
                updated_at=params.current_datetime,
            ),
        )
        await self.photo_files.sync_file_usages(
            attached_file_ids=frozenset({uploaded.file.id}),
            detached_file_ids=frozenset({old_id})
            if old_id and old_id != uploaded.file.id
            else frozenset(),
            orphaned_at=params.current_datetime,
        )
        return updated

    async def read_photo(self, *, params: ResumeTargetParams) -> bytes:
        resume = await self.storage.get_resume(
            resume_id=params.resume_id,
            author_username=params.author_username,
        )
        file_id = resume.content.profile.photo_file_id
        if not file_id:
            raise FilePurposeNotAllowedError
        await self.photo_files.ensure_photo_file_allowed(file_id=file_id)
        return await self.photo_files.download_file(file_id=file_id)

    async def delete_resume(self, *, params: DeleteResumeParams) -> None:
        existing = await self.storage.get_resume(
            resume_id=params.resume_id,
            author_username=params.author_username,
        )
        await self.storage.delete_resume(
            resume_id=params.resume_id,
            author_username=params.author_username,
        )
        file_id = existing.content.profile.photo_file_id
        if file_id:
            await self.photo_files.sync_file_usages(
                attached_file_ids=frozenset(),
                detached_file_ids=frozenset({file_id}),
                orphaned_at=params.current_datetime,
            )

    async def export_resume(self, *, params: ExportResumeParams) -> ResumeExport:
        existing = await self.storage.get_resume(
            resume_id=params.resume_id,
            author_username=params.author_username,
        )
        file_id = params.data.content.profile.photo_file_id
        if file_id and file_id != existing.content.profile.photo_file_id:
            raise FilePurposeNotAllowedError
        photo_content = (
            await self.read_photo(
                params=ResumeTargetParams(
                    resume_id=params.resume_id,
                    author_username=params.author_username,
                ),
            )
            if file_id
            else b""
        )
        return self.exporter.export_resume(params=params.data, photo_content=photo_content)
