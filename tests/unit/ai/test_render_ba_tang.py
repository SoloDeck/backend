"""Ba tầng quyền sửa mẫu — kiểm ngay trên TỜ GIẤY, không chỉ trên cấu trúc dữ liệu.

`test_template_blocks.py` khoá phần chính sách (mục nào tắt được). Ở đây khoá phần hệ quả:
tắt rồi thì mục có thật sự biến khỏi bản gửi khách không, có còn quay lại được ở màn soạn
không, và số điều có còn liền mạch không.

Số điều là chỗ dễ vỡ nhất: bộ đếm `ns.n` nằm ngoài `{% if %}` thì tắt Điều 6 xong hợp đồng
nhảy 5 → 7, khách đọc tưởng mất một trang.  #Huynh
"""

import html as html_lib
import re

from src.ai.contract_generator.application.render import ContractPdfRenderer
from src.ai.contract_generator.schemas.contract_document import ContractDocument
from src.ai.proposal_generator.application.render import ProposalPdfRenderer
from src.ai.proposal_generator.schemas.proposal_document import ProposalDocument
from src.modules.admin.application.template_preview import render_template_preview
from src.shared.domain.template_blocks import (
    CONTRACT_CLAUSE_DEFAULTS,
    CONTRACT_HIDEABLE,
    CONTRACT_SECTION_DEFAULTS,
    PROPOSAL_HIDEABLE,
    PROPOSAL_SECTION_DEFAULTS,
)


def _so_muc(html: str) -> list[int]:
    """Số thứ tự các đầu mục theo đúng thứ tự in ra."""
    return [int(x) for x in re.findall(r"<h2[^>]*>(?:Điều\s+)?(\d+)\.", html)]


def _bao_gia(**kwargs) -> ProposalDocument:
    mac_dinh = {
        "freelancer_name": "A",
        "client_name": "B",
        "project_type": "Thiết kế",
        "proposal_date": "ngày 01 tháng 01 năm 2026",
        "project_overview": "Tổng quan dự án",
        "scope_of_work": ["Việc 1"],
        "deliverables": ["Sản phẩm 1"],
        "timeline": "4 tuần",
        "pricing": "10.000.000 VND",
        "payment_terms": "Đặt cọc 50%",
        "assumptions": "Khách cấp tư liệu",
        "standard_terms": "Điều khoản chuẩn",
        "out_of_scope": ["Chi phí in ấn"],
    }
    return ProposalDocument(**{**mac_dinh, **kwargs})


def _hop_dong(**kwargs) -> ContractDocument:
    mac_dinh = {
        "freelancer_name": "A",
        "client_name": "B",
        "contract_number": "HD-2026-001",
        "contract_date": "ngày 01 tháng 01 năm 2026",
        "scope_of_work": "Nội dung công việc",
        "payment_terms": "Thanh toán 2 đợt",
        "ip_ownership": "Bàn giao quyền",
        "termination_clause": "Báo trước 15 ngày",
        "custom_clauses": "Điều khoản riêng",
        "standard_terms": "Điều khoản chuẩn",
    }
    return ContractDocument(**{**mac_dinh, **kwargs})


class TestTatMucTrenBanGuiKhach:
    def test_bao_gia_tat_mot_muc_thi_muc_do_bien_mat(self):
        html = ProposalPdfRenderer().render_html(
            _bao_gia(hidden_sections=["project_overview"]), editable=False
        )
        assert "Tổng quan dự án" not in html
        # Mục tầng 2 ngay cạnh vẫn còn — tắt là tắt ĐÚNG một mục, không kéo theo hàng xóm.
        assert "Sản phẩm 1" in html

    def test_hop_dong_tat_bao_mat_thi_dieu_do_bien_mat_shtt_van_con(self):
        html = ContractPdfRenderer().render_html(
            _hop_dong(hidden_sections=["confidentiality"]), editable=False
        )
        assert "Bảo Mật Thông Tin" not in html
        assert "Quyền Sở Hữu Trí Tuệ" in html

    def test_khoa_ngoai_danh_sach_cho_phep_khong_tat_duoc_gi(self):
        # Không có allowlist thì đây là cửa sau để bỏ mục TIỀN khỏi tờ giấy gửi khách.
        html = render_template_preview(
            "proposal", {"hidden_sections": ["pricing", "deliverables"]}
        )
        # `data-tat` trần cũng khớp luật CSS ở phần <style>, nên bám thuộc tính thật.
        assert 'data-tat="1"' not in html


class TestSoMucLienMach:
    def test_bao_gia_tat_bon_muc_van_danh_so_lien_mach(self):
        day = _so_muc(
            ProposalPdfRenderer().render_html(
                _bao_gia(
                    hidden_sections=[
                        "project_overview",
                        "additional_terms",
                        "assumptions",
                        "standard_terms",
                    ]
                ),
                editable=False,
            )
        )
        assert day == list(range(1, len(day) + 1))

    def test_hop_dong_tat_bon_dieu_van_danh_so_lien_mach(self):
        day = _so_muc(
            ContractPdfRenderer().render_html(
                _hop_dong(
                    hidden_sections=[
                        "confidentiality",
                        "termination_clause",
                        "standard_terms",
                        "custom_clauses",
                    ]
                ),
                editable=False,
            )
        )
        assert day == list(range(1, len(day) + 1))

    def test_tat_bot_thi_tong_so_dieu_giam_dung_bay_nhieu(self):
        du = _so_muc(ContractPdfRenderer().render_html(_hop_dong(), editable=False))
        thieu = _so_muc(
            ContractPdfRenderer().render_html(
                _hop_dong(hidden_sections=["confidentiality", "standard_terms"]),
                editable=False,
            )
        )
        assert len(du) - len(thieu) == 2


class TestManSoanVanThayMucDaTat:
    def test_moi_muc_tang_3_bi_tat_van_hien_o_man_soan_de_bat_lai_duoc(self):
        """Nếu tắt xong mục biến khỏi CẢ màn soạn thì admin mất luôn đường bật lại.

        Quét HẾT tầng 3 chứ không lấy một mục làm đại diện: điều kiện `editable or ...` viết
        tay ở từng mục trong Jinja, sót một chỗ là mục đó thành cửa một chiều.

        Cùng tinh thần `keep_untitled` của `collect_extra_sections`: chế độ soạn hiện đủ mọi
        chỗ bấm, chế độ gửi khách mới lọc.
        """
        for loai, tap, nhan in (
            ("contract", CONTRACT_HIDEABLE, CONTRACT_SECTION_DEFAULTS),
            ("proposal", PROPOSAL_HIDEABLE, PROPOSAL_SECTION_DEFAULTS),
        ):
            for khoa in tap:
                html = render_template_preview(loai, {"hidden_sections": [khoa]})
                # Escape vì Jinja bật autoescape: "Ghi Chú & Giả Định" in ra thành "&amp;".
                ten = html_lib.escape(nhan[khoa]["vi"], quote=False)
                assert ten in html, f"{loai}/{khoa}: tắt xong mất luôn ở màn soạn"
                assert 'data-tat="1"' in html, f"{loai}/{khoa}: thiếu dấu đã tắt"
                assert "đã tắt" in html

    def test_man_soan_van_danh_so_day_du(self):
        html = render_template_preview("contract", {"hidden_sections": ["confidentiality"]})
        day = _so_muc(html)
        assert day == list(range(1, len(day) + 1))


class TestKhongInDoanVanTrong:
    def test_ba_dieu_dung_dau_nhay_tho_de_rong_khong_sinh_the_p_trong(self):
        """`scope_of_work` / `payment_terms` / `termination_clause` từng in `<p></p>` trần.

        Trên bản gửi khách nó thành một khoảng trắng vô nghĩa dưới tiêu đề — trông như tài
        liệu lỗi.
        """
        html = ContractPdfRenderer().render_html(
            ContractDocument(freelancer_name="A", client_name="B"), editable=False
        )
        assert not re.search(r"<p[^>]*>\s*</p>", html)

    def test_shtt_chi_con_mot_nguon_chu_mac_dinh(self):
        """`contract.html` từng giấu một bản chữ mặc định THỨ HAI cho Điều SHTT ngay trong Jinja.

        Hai nguồn thì admin sửa `CONTRACT_CLAUSE_DEFAULTS` xong vẫn thấy chữ cũ trên giấy, mà
        không có gì chỉ ra vì sao — trái hẳn chú thích "nguồn sự thật duy nhất" của module.
        """
        html = ContractPdfRenderer().render_html(
            ContractDocument(freelancer_name="A", client_name="B"), editable=False
        )
        assert CONTRACT_CLAUSE_DEFAULTS["ip_ownership"] in html
