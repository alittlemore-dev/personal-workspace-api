from datetime import datetime, timedelta

from dishka.integrations.taskiq import FromDishka, inject

from core.files.services import FileOrphanCleanupService
from core.resumes.services import ResumePhotoOrphanCleanupService
from entrypoints.taskiq.broker import broker
from infra.config.constants import constants
from infra.config.settings import settings


@broker.task(
    constants.taskiq.file_orphan_prune_task_name,
    schedule=[
        {
            "schedule_id": constants.taskiq.file_orphan_prune_task_name,
            "interval": settings.taskiq.file_orphan_prune_interval_seconds,
        },
    ],
)
@inject(patch_module=True)
async def prune_file_orphans(
    service: FromDishka[FileOrphanCleanupService],
    photo_service: FromDishka[ResumePhotoOrphanCleanupService],
    current_datetime: FromDishka[datetime],
) -> dict[str, int]:
    result = await service.prune(
        cutoff=current_datetime - timedelta(seconds=settings.files.orphan_retention_seconds),
    )
    photo_result = await photo_service.prune(
        cutoff=current_datetime - timedelta(seconds=settings.files.orphan_retention_seconds),
    )
    return {
        "scannedCount": result.scanned_count + photo_result.scanned_count,
        "deletedCount": result.deleted_count + photo_result.deleted_count,
        "failedCount": result.failed_count + photo_result.failed_count,
        "skippedInUseCount": result.skipped_in_use_count + photo_result.skipped_in_use_count,
    }
