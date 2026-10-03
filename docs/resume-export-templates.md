# Resume export templates

Each theme lives in `src/infra/resume_export/templates/<theme>/` and has three editable files:

- `pdf.html.j2` contains the PDF layout and Jinja conditions/loops.
- `pdf.css` contains the PDF typography, colors, spacing, and page frames. The HTML template includes it with Jinja.
- `resume.docx` is a Word template rendered with docxtpl. Paragraph styles and page settings can be edited in Word or LibreOffice; `{%p ... %}` paragraphs control optional blocks and lists.

The exporter builds one shared context in `src/infra/resume_export/context.py`. Templates receive `content`, `labels`, `display_name`, `contacts`, `experiences`, `educations`, and `certifications`. The view lists include dates formatted using the required `content.settings.date_format` setting (`monthYear`, `monthYearNumeric`, `fullDate`, or `year`). `monthYear` uses localized short month names, numeric months use `MM.YYYY`, and full dates use `DD.MM.YYYY` in Russian or `MM/DD/YYYY` in English. Blank project roles inherit the containing experience position in this context; persisted content retains the authored blank role. PDF templates may use the `linebreaks` filter for authored multiline text.

To add a theme, create its three files, add its value to `ResumeThemeEnum`, and expose its translated name in the frontend theme picker. Keep both PDF and DOCX templates in sync for section order and content, then render sample RU and EN resumes in both formats to inspect pagination and text extraction. Page count grows with the content; templates do not shrink typography to fit a target number of pages. The `simple` theme keeps a linear structure for text extraction; `accent` uses the blue layout inspired by the supplied reference PDF.
