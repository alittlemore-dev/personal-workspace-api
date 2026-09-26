from dataclasses import dataclass

from core.files.enums import FilePurpose
from core.files.exceptions import FilePurposeNotAllowedError
from core.files.services import FileOrphanCleanupService, FileService


@dataclass(kw_only=True, slots=True, frozen=True)
class ResumePhotoFileService(FileService):
    async def ensure_photo_file_allowed(self, *, file_id: str) -> None:
        file = await self.get_file(file_id=file_id)
        if file.file.purpose != FilePurpose.ATTACHMENT or file.file.mime_type != "image/jpeg":
            raise FilePurposeNotAllowedError


@dataclass(kw_only=True, slots=True, frozen=True)
class ResumePhotoOrphanCleanupService(FileOrphanCleanupService): ...
