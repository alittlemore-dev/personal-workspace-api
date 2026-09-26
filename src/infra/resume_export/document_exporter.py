import base64
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from docx.shared import Mm
from docxtpl import DocxTemplate, InlineImage
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup
from xhtml2pdf import pisa

from core.resumes.enums import ResumeExportFormatEnum
from core.resumes.exporters import ResumeDocumentExporter
from core.resumes.schemas import ResumeExport, ResumeExportParams
from infra.resume_export.context import ResumeTemplateContext


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeDocumentExporterImpl(ResumeDocumentExporter):
    font_regular_path: Path
    font_bold_path: Path
    font_regular_name: str
    font_bold_name: str

    def export_resume(self, *, params: ResumeExportParams, photo_content: bytes) -> ResumeExport:
        context = ResumeTemplateContext.from_params(params=params).as_dict()
        context["photo_data_url"] = (
            "data:image/jpeg;base64," + base64.b64encode(photo_content).decode("ascii")
            if photo_content
            else ""
        )
        if params.format == ResumeExportFormatEnum.PDF:
            return ResumeExport(
                format=params.format,
                content=self._render_pdf(params=params, context=context),
            )
        if params.format == ResumeExportFormatEnum.DOCX:
            return ResumeExport(
                format=params.format,
                content=self._render_docx(
                    params=params, context=context, photo_content=photo_content
                ),
            )
        message = f"Unsupported resume export format: {params.format}"
        raise ValueError(message)

    def _render_pdf(self, *, params: ResumeExportParams, context: dict[str, object]) -> bytes:
        templates_dir = Path(__file__).parent / "templates"
        environment = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=True,
            undefined=StrictUndefined,
        )
        environment.filters["linebreaks"] = self._linebreaks
        template = environment.get_template(f"{params.theme.value}/pdf.html.j2")
        html = template.render(
            **context,
            font_regular_name=self.font_regular_name,
            font_bold_name=self.font_bold_name,
        )
        output = BytesIO()

        result = pisa.CreatePDF(
            html,
            dest=output,
            encoding="utf-8",
            link_callback=self._resolve_resource,
            context_meta={"title": params.title, "author": params.content.profile.full_name},
            raise_exception=True,
        )
        if result.err:
            message = f"Failed to render {params.theme.value} PDF resume"
            raise ValueError(message)
        return output.getvalue()

    def _render_docx(
        self, *, params: ResumeExportParams, context: dict[str, object], photo_content: bytes
    ) -> bytes:
        template_path = Path(__file__).parent / "templates" / params.theme.value / "resume.docx"
        template = DocxTemplate(template_path)
        context["photo"] = (
            InlineImage(template, BytesIO(photo_content), width=Mm(26)) if photo_content else ""
        )
        environment = Environment(undefined=StrictUndefined, autoescape=True)
        template.render(context, jinja_env=environment, autoescape=True)
        output = BytesIO()
        template.save(output)
        return output.getvalue()

    def _linebreaks(self, value: str) -> Markup:
        return Markup.escape(value).replace("\n", Markup("<br/>"))

    def _resolve_resource(self, uri: str, _basepath: str | None) -> str:
        if uri.startswith("data:image/jpeg;base64,"):
            return uri
        if uri == "resume-font-regular":
            return str(self.font_regular_path)
        if uri == "resume-font-bold":
            return str(self.font_bold_path)
        message = f"Unexpected resume template resource: {uri}"
        raise ValueError(message)
