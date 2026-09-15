from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from core.resumes.exporters import ResumeDocumentExporter
from core.resumes.storages import ResumesStorage
from core.resumes.use_cases import ResumesUseCase
from infra.config.constants import constants
from infra.postgresql.storages.resumes import ResumesDatabaseStorage
from infra.resume_export.document_exporter import ResumeDocumentExporterImpl


class ResumesProvider(Provider):
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
    ) -> ResumesUseCase:
        return ResumesUseCase(storage=storage, exporter=exporter)
