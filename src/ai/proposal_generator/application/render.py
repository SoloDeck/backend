from pathlib import Path
from io import BytesIO

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from ..schemas.ProposalDocument import ProposalDocument


class ProposalPdfRenderer:

    def __init__(self):
        templates_dir = (
            Path(__file__)
            .parent.parent
            / "templates"
        )

        self.env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=True
        )

    def render_html(
        self,
        document: ProposalDocument
    ) -> str:

        template = self.env.get_template(
            "template.html"
        )

        return template.render(
            **document.model_dump()
        )

    def render_pdf(
        self,
        document: ProposalDocument
    ) -> bytes:

        html_content = self.render_html(
            document
        )

        pdf_buffer = BytesIO()

        HTML(
            string=html_content
        ).write_pdf(
            target=pdf_buffer
        )

        return pdf_buffer.getvalue()