"""Ngữ cảnh gửi cho máy soạn báo giá — thuần chuỗi, KHÔNG gọi LLM.

Cùng gốc bệnh với lead_qualifier: `project_description` chính là `deals.notes`, tức ô "Nội
dung yêu cầu" trên giao diện, nhưng bị dán nhãn "Ghi chú nội bộ" và xếp vào khối mà prompt
ra luật KHÔNG được lấy timeline. Khách ghi "Thời gian build: 5 tháng", freelancer dán nguyên
văn vào, và bản báo giá GỬI CHO KHÁCH vẫn ghi "hai bên thống nhất sau".  #Huynh
"""

from unittest.mock import MagicMock

from src.ai.proposal_generator.application.service import (
    PROPOSAL_OWN_HEADING,
    PROPOSAL_REQUIREMENT_HEADING,
    ProposalGenerationService,
)
from src.ai.proposal_generator.schemas.proposal_generation_input import (
    ProposalGenerationInput,
)
from src.ai.shared.prompt import load_prompt

BRIEF = "Thời gian build: 5 tháng. Ngân sách: 700 triệu. Module: A, B, C."


def _context(**fields) -> str:
    request = ProposalGenerationInput(
        client_name="Khách A", project_type="Website bán hàng", **fields
    )
    return ProposalGenerationService(provider=MagicMock())._build_context(request)


def test_noi_dung_yeu_cau_nam_trong_khoi_can_cu_soan_bao_gia() -> None:
    ctx = _context(project_description=BRIEF)

    assert ctx.startswith(PROPOSAL_REQUIREMENT_HEADING)
    assert f"- Nội dung yêu cầu: {BRIEF}" in ctx.partition(PROPOSAL_OWN_HEADING)[0]


def test_khong_con_dan_nhan_ghi_chu_noi_bo() -> None:
    """Đúng cái nhãn này làm mốc "5 tháng" bị bỏ qua khi soạn báo giá."""
    ctx = _context(project_description=BRIEF)

    assert "Ghi chú nội bộ" not in ctx
    assert "THÔNG TIN FREELANCER TỰ NHẬP" not in ctx


def test_gia_se_chao_va_muc_gia_nam_o_khoi_freelancer_tu_chon() -> None:
    """Ba thứ này là LỰA CHỌN của freelancer, không được viết như thể khách yêu cầu."""
    ctx = _context(
        project_description=BRIEF,
        freelancer_estimated_value="90000000",
        pricing_tier="premium",
        urgency="gấp",
    )

    requirement, sep, own = ctx.partition(PROPOSAL_OWN_HEADING)
    assert sep == PROPOSAL_OWN_HEADING
    assert "90000000" not in requirement
    assert "premium" not in requirement
    assert "90000000" in own
    assert "premium" in own


def test_khong_co_lua_chon_rieng_thi_khong_in_khoi_do() -> None:
    ctx = _context(project_description=BRIEF)

    assert PROPOSAL_OWN_HEADING not in ctx


def test_cac_ben_luon_con_o_cuoi() -> None:
    """Tên khách và tên freelancer đi thẳng vào bản PDF gửi đi — mất là hỏng báo giá."""
    ctx = _context(project_description=BRIEF, freelancer_name="Huynh")

    assert "## CÁC BÊN" in ctx
    assert "- Khách hàng: Khách A" in ctx
    assert "- Freelancer: Huynh" in ctx


def test_tieu_de_khoi_khop_voi_prompt() -> None:
    """Prompt gọi tên hai khối nguyên văn để ra luật timeline — sửa lệch là AI viết bậy."""
    prompt = load_prompt("proposal_generator")

    assert PROPOSAL_REQUIREMENT_HEADING in prompt
    assert PROPOSAL_OWN_HEADING in prompt


def test_van_giu_luat_khong_bia_moc_thoi_gian() -> None:
    """Nới luật cho ô "Nội dung yêu cầu" KHÔNG được kéo theo việc cho phép bịa thời hạn.

    Bản báo giá gửi thẳng cho khách; bịa một mốc là hứa hộ freelancer điều họ chưa đồng ý.
    """
    prompt = load_prompt("proposal_generator")

    assert "hai bên thống nhất sau khi chốt phạm vi công việc" in prompt
    assert "TUYỆT ĐỐI KHÔNG tự nghĩ ra" in prompt
