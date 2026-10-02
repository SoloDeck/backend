"""Gửi hợp đồng giờ dựng PDF rồi gửi EMAIL thật cho khách — test không được để thư bay ra ngoài."""

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from src.ai.contract_generator.application.render import ContractPdfRenderer

FAKE_PDF = b"%PDF-1.4 hop dong gia lap"


@pytest.fixture(autouse=True)
def gui_email_gia() -> Iterator[AsyncMock]:
    """Thay `send_email` và bước dựng PDF bằng bản giả cho MỌI bài trong thư mục này.

    `POST /contracts/{id}/send` dựng PDF rồi gửi thư tới email khách. Bài nào chỉ cần một
    hợp đồng ở trạng thái đã gửi (làm bước chuẩn bị) không nên phải tự nhớ chặn SMTP — quên
    một chỗ là thư bay thật tới hộp thư của người đang chạy test. Bài nào muốn kiểm nội dung
    thư thì nhận fixture này làm tham số để đọc `await_args`.

    `autospec=True` ép bản giả có ĐÚNG chữ ký của `send_email` thật: sau này đổi tên/bỏ tham số
    mà chỗ gọi quên theo thì bài tự đỏ, thay vì mock trần nuốt hết mọi tham số.

    PDF cũng giả: WeasyPrint cần thư viện hệ thống (Pango/GTK) mà máy Windows chạy test
    thường không có. Việc PDF dựng ra được thật thì do `tests/unit/ai/test_render_pdf_that.py`
    kiểm (bỏ qua trên máy thiếu thư viện, chạy thật trên CI).
    """
    with (
        patch("src.shared.email.smtp.send_email", autospec=True) as mock,
        patch.object(ContractPdfRenderer, "render_pdf", return_value=FAKE_PDF),
    ):
        yield mock
