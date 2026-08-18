from io import BytesIO
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.shared.domain.template_blocks import (
    PROPOSAL_CLAUSE_DEFAULTS,
    PROPOSAL_SECTION_DEFAULTS,
)

from ..schemas.proposal_document import ProposalDocument


class ProposalPdfRenderer:
    def __init__(self):
        templates_dir = Path(__file__).parent.parent / "templates"

        self.env = Environment(loader=FileSystemLoader(templates_dir), autoescape=True)

    def render_html(self, document: ProposalDocument, *, editable: bool = False) -> str:
        """`editable=True`: render CẢ những mục đang trống, thành thẻ `data-field` rỗng.

        Không có cờ này thì báo giá soạn từ khung là một bài toán con-gà-quả-trứng: 5/10 mục bọc
        trong `{% if %}` nên rỗng là biến mất, mà biến mất thì không có chỗ bấm để nhập nội dung.
        Freelancer không có cách nào đặt điều khoản thanh toán hay hạn hiệu lực nếu AI chưa điền
        trước.

        Bản gửi khách và PDF luôn `editable=False` → mục rỗng biến mất như cũ, không rò ra
        ngoài.  #Huynh
        """
        template = self.env.get_template("template.html")

        return template.render(
            **document.model_dump(),
            editable=editable,
            # Tên mục là DỮ LIỆU: bảng mặc định ở một nơi duy nhất (Python),
            # template chỉ tra bảng. Mẫu của admin ghi đè qua `section_titles`.
            section_defaults=PROPOSAL_SECTION_DEFAULTS,
            clause_defaults=PROPOSAL_CLAUSE_DEFAULTS,
        )

    def render_pdf(self, document: ProposalDocument) -> bytes:
        from weasyprint import HTML  # lazy: requires GTK system libs

        # CỐ Ý không truyền `editable`: tờ giấy khách nhận không bao giờ có ô rỗng.
        html_content = self.render_html(document)

        pdf_buffer = BytesIO()

        HTML(string=html_content).write_pdf(target=pdf_buffer)

        return pdf_buffer.getvalue()
