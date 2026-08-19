from io import BytesIO
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.shared.domain.template_blocks import (
    CONTRACT_CLAUSE_DEFAULTS,
    CONTRACT_SECTION_DEFAULTS,
)

from ..schemas.contract_document import ContractDocument


class ContractPdfRenderer:
    """Render hợp đồng ra HTML (xem trước) và PDF (tải về) từ CÙNG một template.

    Song song với ``ProposalPdfRenderer``. Bản trên màn hình và bản khách nhận render
    từ đúng một file ``contract.html`` nên KHÔNG THỂ lệch — đó là điều khiến tờ hợp đồng
    trước đây (đổ field thô ở frontend) nhìn như lừa đảo.  #Huynh
    """

    def __init__(self):
        templates_dir = Path(__file__).parent.parent / "templates"

        self.env = Environment(loader=FileSystemLoader(templates_dir), autoescape=True)

    def render_html(self, document: ContractDocument, *, editable: bool = False) -> str:
        template = self.env.get_template("contract.html")

        # `editable=True`: render CẢ những điều khoản đang trống (revision/ip/termination/
        # bổ sung) thành ô rỗng có `data-field` để người dùng bấm vào gõ. Bản đọc-only/PDF
        # thì bỏ qua điều trống cho tờ giấy sạch. Cùng một template, khác đúng một cờ.  #Huynh
        return template.render(
            **document.model_dump(),
            editable=editable,
            # Tên mục là DỮ LIỆU: bảng mặc định ở một nơi duy nhất (Python),
            # template chỉ tra bảng. Mẫu của admin ghi đè qua `section_titles`.
            section_defaults=CONTRACT_SECTION_DEFAULTS,
            clause_defaults=CONTRACT_CLAUSE_DEFAULTS,
        )

    def render_pdf(self, document: ContractDocument) -> bytes:
        from weasyprint import HTML  # lazy: requires GTK system libs

        html_content = self.render_html(document)

        pdf_buffer = BytesIO()

        HTML(string=html_content).write_pdf(target=pdf_buffer)

        return pdf_buffer.getvalue()
