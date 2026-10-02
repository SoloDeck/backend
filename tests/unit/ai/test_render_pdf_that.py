"""Dựng PDF THẬT bằng WeasyPrint — thứ duy nhất trong repo chạy `render_pdf` không qua mock.

`POST /proposals/{id}/send` và `POST /contracts/{id}/send` giờ đính kèm file PDF vào thư gửi
khách, nên hai nút đó phụ thuộc WeasyPrint chạy được. Các test của endpoint đều thay
`render_pdf` bằng bản giả (máy Windows chạy test không có thư viện hệ thống Pango/GTK), nên
nếu không có bài này thì không bài nào chứng minh PDF dựng ra được.

Máy thiếu thư viện native thì BỎ QUA chứ không đỏ: chuyện đó là môi trường, không phải lỗi
code. Trên CI (Linux, đã cài thư viện) bài chạy thật.  #Huynh
"""

import pytest

from src.ai.contract_generator.application.render import ContractPdfRenderer
from src.ai.proposal_generator.application.render import ProposalPdfRenderer
from tests.unit.ai.test_render_ba_tang import _bao_gia, _hop_dong


def _render(render):  # type: ignore[no-untyped-def]
    try:
        return render()
    except OSError as exc:  # WeasyPrint không nạp được Pango/GTK
        pytest.skip(f"WeasyPrint thiếu thư viện hệ thống trên máy này: {exc}")


def test_bao_gia_dung_ra_file_pdf_hop_le() -> None:
    pdf = _render(lambda: ProposalPdfRenderer().render_pdf(_bao_gia()))
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 5_000, "PDF trống trơn thì không ai đọc được gì"


def test_hop_dong_dung_ra_file_pdf_hop_le() -> None:
    pdf = _render(lambda: ContractPdfRenderer().render_pdf(_hop_dong()))
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 5_000
