from dataclasses import dataclass
from pathlib import Path

from core.resumes.enums import ResumeThemeEnum
from core.resumes.exporters import ResumeDocumentExporter
from core.resumes.schemas import ResumeExport, ResumeExportParams
from infra.resume_export.renderers.accent import AccentResumeRenderer
from infra.resume_export.renderers.simple import SimpleResumeRenderer


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeDocumentExporterImpl(ResumeDocumentExporter):
    font_regular_path: Path
    font_bold_path: Path
    font_regular_name: str
    font_bold_name: str

    def export_resume(self, *, params: ResumeExportParams) -> ResumeExport:
        renderer_type = {
            ResumeThemeEnum.SIMPLE: SimpleResumeRenderer,
            ResumeThemeEnum.ACCENT: AccentResumeRenderer,
        }[params.theme]
        renderer = renderer_type(
            font_regular_path=self.font_regular_path,
            font_bold_path=self.font_bold_path,
            font_regular_name=self.font_regular_name,
            font_bold_name=self.font_bold_name,
        )
        return renderer.export_resume(params=params)
