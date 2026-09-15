from abc import ABC, abstractmethod

from core.resumes.schemas import ResumeExport, ResumeExportParams


class ResumeDocumentExporter(ABC):
    @abstractmethod
    def export_resume(self, *, params: ResumeExportParams) -> ResumeExport:
        raise NotImplementedError
