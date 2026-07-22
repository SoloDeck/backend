"""Gói 3 — ghép ngữ cảnh nghề vào prompt lead qualifier.

Test hàm thuần `build_qualifier_prompt` (string vào, string ra) nên KHÔNG cần gọi Groq.
"""

from src.ai.lead_qualifier.chain import build_qualifier_prompt


def test_chen_nghe_va_scam_khi_co():
    p = build_qualifier_prompt(
        "SYSTEM PROMPT",
        "khách cần web bán hàng",
        profession="Thiết kế UI/UX",
        scam_hint="đòi làm vài mẫu miễn phí",
    )
    assert "Nghề của freelancer: Thiết kế UI/UX" in p
    assert "Mẫu lừa đảo phổ biến của nghề này: đòi làm vài mẫu miễn phí" in p
    assert "Client Inquiry:" in p
    assert "khách cần web bán hàng" in p
    # ngữ cảnh nghề phải nằm TRƯỚC phần inquiry
    assert p.index("Nghề của freelancer") < p.index("Client Inquiry:")


def test_khong_nghe_thi_prompt_nhu_cu():
    p = build_qualifier_prompt("SYSTEM PROMPT", "khách cần web", None, None)
    assert "Nghề của freelancer" not in p
    assert "Mẫu lừa đảo" not in p
    assert "Client Inquiry:" in p
    assert "khách cần web" in p


def test_co_nghe_nhung_khong_co_scam():
    p = build_qualifier_prompt("SYS", "abc", profession="Lập trình", scam_hint=None)
    assert "Nghề của freelancer: Lập trình" in p
    assert "Mẫu lừa đảo" not in p
