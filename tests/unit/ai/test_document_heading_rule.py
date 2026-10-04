"""Đường kẻ ngăn các mục của báo giá và hợp đồng nằm TRÊN đầu mục, không nằm dưới.

Trước đây mỗi đầu mục (`h2`) có một đường kẻ ngay DƯỚI nó: tiêu đề, kẻ ngang, nội dung, rồi đầu
mục kế tiếp ngay sau đó. Người đọc thấy nội dung bị kẻ tách khỏi tiêu đề của chính nó và nằm sát
đầu mục tiếp theo, nên hiểu nhầm là nội dung không thuộc mục nào (hoặc thuộc mục kế tiếp). Đặt
đường kẻ ở TRÊN mỗi đầu mục thì mỗi mục là một khối: kẻ — tiêu đề — nội dung, rồi mới tới đường
kẻ của mục sau.

Cùng một template dựng cả bản xem trước trên màn hình lẫn file PDF gửi khách, nên giữ luật này ở
đây là giữ cho cả hai.  #Huynh
"""

import re
from pathlib import Path

import pytest

TEMPLATES = {
    "bao_gia": Path("src/ai/proposal_generator/templates/template.html"),
    "hop_dong": Path("src/ai/contract_generator/templates/contract.html"),
}


def _luat_h2(html: str) -> str:
    """Thân của luật CSS `h2 { ... }` — không lẫn với `h2[data-tat] { ... }` (mục đang tắt)."""
    khop = re.search(r"(?m)^\s*h2\s*\{([^}]*)\}", html)
    assert khop, "template không còn luật CSS cho đầu mục h2"
    return khop.group(1)


@pytest.mark.parametrize("ten", TEMPLATES)
def test_duong_ke_nam_tren_dau_muc(ten: str) -> None:
    luat = _luat_h2(TEMPLATES[ten].read_text(encoding="utf-8"))
    assert "border-top" in luat, "đường kẻ phải ở TRÊN đầu mục"
    assert "border-bottom" not in luat, (
        "đường kẻ dưới đầu mục chen giữa tiêu đề và nội dung của nó — người đọc sẽ tưởng nội "
        "dung thuộc mục kế tiếp"
    )


@pytest.mark.parametrize("ten", TEMPLATES)
def test_co_khoang_dem_giua_duong_ke_va_chu_tieu_de(ten: str) -> None:
    """Kẻ sát rạt vào chữ thì trông như gạch đầu chữ; phải có `padding-top`."""
    luat = _luat_h2(TEMPLATES[ten].read_text(encoding="utf-8"))
    assert "padding-top" in luat
