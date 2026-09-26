from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from core.files.enums import FilePurpose
from core.files.file_name_generators import FileNameGenerator
from core.files.schemas import FileOrphanCleanupConfig, FileRule, FileRules, FileServiceConfig
from core.files.storages import FileStorage
from core.resumes.exporters import ResumeDocumentExporter
from core.resumes.services import ResumePhotoFileService, ResumePhotoOrphanCleanupService
from core.resumes.storages import ResumesStorage
from core.resumes.use_cases import ResumesUseCase
from infra.config.constants import constants
from infra.files.processors import ResumePhotoContentProcessor
from infra.postgresql.storages.resumes import ResumesDatabaseStorage
from infra.resume_export.document_exporter import ResumeDocumentExporterImpl
from infra.s3.clients import S3ClientBundle, S3PrivateResumeFileClient


class ResumesProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_resume_photo_client(
        self,
        clients: S3ClientBundle,
    ) -> S3PrivateResumeFileClient:
        return S3PrivateResumeFileClient(
            internal_client=clients.internal,
            bucket_name=constants.minio_buckets.resume_private,
        )

    @provide(scope=Scope.REQUEST)
    async def provide_resume_photo_service(
        self,
        photo_client: S3PrivateResumeFileClient,
        file_storage: FileStorage,
        file_name_generator: FileNameGenerator,
    ) -> ResumePhotoFileService:
        return ResumePhotoFileService(
            file_client=photo_client,
            file_storage=file_storage,
            file_name_generator=file_name_generator,
            file_content_processor=ResumePhotoContentProcessor(
                max_dimension=constants.files.resume_photo_max_dimension,
            ),
            config=FileServiceConfig(
                namespace=constants.minio_buckets.resume_private,
                rules=FileRules(
                    values={
                        FilePurpose.ATTACHMENT: FileRule(
                            folder="photos",
                            allowed_mime_types=frozenset({"image/jpeg"}),
                            max_size_bytes=constants.files.resume_photo_max_size_bytes,
                        ),
                    },
                ),
            ),
        )

    @provide(scope=Scope.REQUEST)
    async def provide_resume_photo_cleanup(
        self,
        photo_client: S3PrivateResumeFileClient,
        file_storage: FileStorage,
    ) -> ResumePhotoOrphanCleanupService:
        return ResumePhotoOrphanCleanupService(
            file_client=photo_client,
            file_storage=file_storage,
            config=FileOrphanCleanupConfig(
                namespace=constants.minio_buckets.resume_private,
                batch_size=constants.files.orphan_cleanup_batch_size,
            ),
        )

    @provide(scope=Scope.REQUEST)
    async def provide_resumes_storage(self, session: AsyncSession) -> ResumesStorage:
        return ResumesDatabaseStorage(session=session)

    @provide(scope=Scope.APP)
    async def provide_resume_document_exporter(self) -> ResumeDocumentExporter:
        return ResumeDocumentExporterImpl(
            font_regular_path=constants.resume_export.font_regular_path,
            font_bold_path=constants.resume_export.font_bold_path,
            font_regular_name=constants.resume_export.font_regular_name,
            font_bold_name=constants.resume_export.font_bold_name,
        )

    @provide(scope=Scope.REQUEST)
    async def provide_resumes_use_case(
        self,
        storage: ResumesStorage,
        exporter: ResumeDocumentExporter,
        photo_files: ResumePhotoFileService,
    ) -> ResumesUseCase:
        return ResumesUseCase(storage=storage, exporter=exporter, photo_files=photo_files)
