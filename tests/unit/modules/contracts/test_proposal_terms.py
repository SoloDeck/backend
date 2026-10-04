"""Phần hợp đồng lấy từ báo giá đã chốt — thuần hàm, không DB.

Điều cần khoá: tiền trong hợp đồng đọc từ ĐÚNG nguồn mà bảng báo giá, task thu tiền và hoá đơn đang
đọc (`resolve_cost_items`), và không bao giờ bịa ra một bảng khi báo giá không có hạng mục nào.
"""

from src.modules.contracts.application.proposal_terms import (
    PAYMENT_METHOD_SENTENCE,
    apply_payment_from_proposal,
    apply_scope_from_proposal,
    payment_terms_from_proposal,
    schedule_from_proposal,
    scope_from_proposal,
)

BAO_GIA = {
    "pricing": {"total": 12_000_000, "currency": "VND"},
    "pricing_items": [
        {"label": "Khảo sát và wireframe", "amount": 3_600_000, "due_type": "on_signing"},
        {"label": "Thiết kế giao diện (UI)", "amount": 4_800_000},
        {
            "label": "Bàn giao",
            "amount": 3_600_000,
            "due_type": "custom",
            "due_note": "Trong 7 ngày sau nghiệm thu",
        },
    ],
    "scope_of_work": ["Khảo sát yêu cầu", "Thiết kế giao diện"],
    "deliverables": ["File Figma", "UI kit"],
    "out_of_scope": ["Lập trình giao diện"],
}


class TestScheduleFromProposal:
    def test_moi_hang_muc_la_mot_dong_dung_so_tien_va_moc_thu(self) -> None:
        lines, total = schedule_from_proposal(BAO_GIA)

        assert [(x.description, x.amount, x.due_date) for x in lines] == [
            ("Khảo sát và wireframe", "3.600.000 VND", "Khi ký hợp đồng"),
            ("Thiết kế giao diện (UI)", "4.800.000 VND", "Khi hoàn thành hạng mục"),
            ("Bàn giao", "3.600.000 VND", "Trong 7 ngày sau nghiệm thu"),
        ]
        assert total == "12.000.000 VND"

    def test_tong_la_tong_cac_dong_khong_phai_so_khai_rieng(self) -> None:
        content = {**BAO_GIA, "pricing": {"total": 99_000_000, "currency": "VND"}}

        _, total = schedule_from_proposal(content)

        assert total == "12.000.000 VND"

    def test_bao_gia_khong_co_hang_muc_thi_khong_dung_bang(self) -> None:
        assert schedule_from_proposal({"pricing": "Giá sẽ báo sau"}) == ([], "")
        assert schedule_from_proposal({}) == ([], "")
        assert schedule_from_proposal(None) == ([], "")

    def test_ngoai_te_giu_nguyen_ma_tien(self) -> None:
        content = {
            "pricing": {
                "total": 1500,
                "currency": "USD",
                "line_items": [{"description": "Design", "amount": 1500}],
            }
        }

        lines, total = schedule_from_proposal(content)

        assert lines[0].amount == "1.500 USD"
        assert total == "1.500 USD"


class TestPaymentTermsFromProposal:
    def test_co_tong_bang_so_va_bang_chu(self) -> None:
        text = payment_terms_from_proposal(BAO_GIA)

        assert text.startswith(
            "Tổng giá trị hợp đồng là 12.000.000 VND (Mười hai triệu đồng Việt Nam)."
        )
        assert PAYMENT_METHOD_SENTENCE in text
        assert "bảng dưới đây" in text

    def test_ngoai_te_chi_ghi_so_khong_boa_cach_doc(self) -> None:
        content = {
            "pricing": {
                "currency": "USD",
                "line_items": [{"description": "Design", "amount": 1500}],
            }
        }

        text = payment_terms_from_proposal(content)

        assert text.startswith("Tổng giá trị hợp đồng là 1.500 USD.")
        assert "đồng Việt Nam" not in text

    def test_khong_hang_muc_thi_rong(self) -> None:
        assert payment_terms_from_proposal({}) == ""
        assert payment_terms_from_proposal(None) == ""


class TestApplyPaymentFromProposal:
    def test_duong_ai_thay_han_doan_model_viet(self) -> None:
        content = {"payment_terms": "Đợt 1: 2.400.000 ₫. Đợt 2: 3.600.000 ₫.", "scope_of_work": "x"}

        out = apply_payment_from_proposal(content, BAO_GIA, replace_text=True)

        assert "2.400.000" not in out["payment_terms"]
        assert out["payment_terms"] == payment_terms_from_proposal(BAO_GIA)
        assert out["scope_of_work"] == "x"

    def test_duong_mau_giu_loi_admin_va_dat_cau_ve_tien_len_truoc(self) -> None:
        content = {"payment_terms": "Mỗi hạng mục thanh toán trong 7 ngày."}

        out = apply_payment_from_proposal(content, BAO_GIA, replace_text=False)

        assert out["payment_terms"] == (
            f"{payment_terms_from_proposal(BAO_GIA)}\nMỗi hạng mục thanh toán trong 7 ngày."
        )

    def test_mau_khong_co_loi_thanh_toan_thi_chi_con_cau_ve_tien(self) -> None:
        out = apply_payment_from_proposal({}, BAO_GIA, replace_text=False)

        assert out == {"payment_terms": payment_terms_from_proposal(BAO_GIA)}

    def test_loi_trang_trong_mau_khong_dem_thanh_dong_trong(self) -> None:
        out = apply_payment_from_proposal({"payment_terms": "   "}, BAO_GIA, replace_text=False)

        assert out["payment_terms"] == payment_terms_from_proposal(BAO_GIA)

    def test_bao_gia_khong_co_hang_muc_thi_giu_nguyen_ca_chu_cua_model(self) -> None:
        content = {"payment_terms": "Hai bên thống nhất bằng văn bản."}

        assert apply_payment_from_proposal(content, {}, replace_text=True) == content
        assert apply_payment_from_proposal(content, None, replace_text=False) == content

    def test_khong_sua_dict_dau_vao(self) -> None:
        content = {"payment_terms": "cũ"}

        apply_payment_from_proposal(content, BAO_GIA, replace_text=True)

        assert content == {"payment_terms": "cũ"}


class TestScopeFromProposal:
    def test_ba_muc_danh_so_lien_mach(self) -> None:
        assert scope_from_proposal(BAO_GIA) == (
            "1. Phạm vi công việc:\n- Khảo sát yêu cầu\n- Thiết kế giao diện\n"
            "2. Sản phẩm bàn giao:\n- File Figma\n- UI kit\n"
            "3. Phạm vi không bao gồm:\n- Lập trình giao diện"
        )

    def test_muc_trong_bi_bo_va_so_duoc_danh_lai(self) -> None:
        content = {"scope_of_work": ["A"], "out_of_scope": ["B"]}

        assert scope_from_proposal(content) == (
            "1. Phạm vi công việc:\n- A\n2. Phạm vi không bao gồm:\n- B"
        )

    def test_scope_cu_dang_doan_nhieu_dong_va_dau_gach_dau_dong(self) -> None:
        content = {"scope_of_work": "- Thiết kế logo\n• In ấn\n\n  * Bàn giao  "}

        assert scope_from_proposal(content) == (
            "1. Phạm vi công việc:\n- Thiết kế logo\n- In ấn\n- Bàn giao"
        )

    def test_dong_trang_trong_danh_sach_bi_bo(self) -> None:
        assert scope_from_proposal({"deliverables": ["", "  ", "File nguồn"]}) == (
            "1. Sản phẩm bàn giao:\n- File nguồn"
        )

    def test_khong_co_gi_thi_rong(self) -> None:
        assert scope_from_proposal({}) == ""
        assert scope_from_proposal(None) == ""
        assert scope_from_proposal({"scope_of_work": []}) == ""


class TestApplyScopeFromProposal:
    def test_dat_sau_cau_dan_cua_mau(self) -> None:
        out = apply_scope_from_proposal({"scope_of_work": "Theo báo giá đã duyệt."}, BAO_GIA)

        assert out["scope_of_work"].startswith("Theo báo giá đã duyệt.\n1. Phạm vi công việc:")

    def test_mau_khong_co_cau_dan_thi_chi_con_phan_tu_bao_gia(self) -> None:
        out = apply_scope_from_proposal({}, BAO_GIA)

        assert out["scope_of_work"] == scope_from_proposal(BAO_GIA)

    def test_bao_gia_khong_co_phan_pham_vi_thi_giu_nguyen(self) -> None:
        content = {"scope_of_work": "Theo báo giá."}

        assert apply_scope_from_proposal(content, {"pricing": "x"}) == content

    def test_khong_sua_dict_dau_vao(self) -> None:
        content = {"scope_of_work": "cũ"}

        apply_scope_from_proposal(content, BAO_GIA)

        assert content == {"scope_of_work": "cũ"}
