"""Test build_proposal_document() — dựng PDF từ CẢ HAI shape của `content`.  #Huynh"""

from src.modules.proposals.application.pdf_content import build_proposal_document

META = {
    "freelancer_name": "Huynh",
    "client_name": "Cong ty ABC",
    "company_name": "Cong ty ABC",
    "project_type": "E-commerce Website",
    "proposal_date": "2026-07-12",
}

# Shape CHÍNH THỨC trong contracts/openapi.yaml — frontend lưu đúng cái này.
DTO_CONTENT = {
    "title": "Bao gia thiet ke website",
    "executive_summary": "Website ban hang tich hop VNPay",
    "scope_of_work": "Thiet ke UI\nLap trinh frontend\nTich hop thanh toan",
    "timeline": {
        "start_date": "2026-08-01",
        "end_date": "2026-10-01",
        "milestones": [{"title": "Ban giao thiet ke", "due_date": "2026-08-15"}],
    },
    "pricing": {
        "currency": "VND",
        "total": 50000000,
        "line_items": [
            {
                "description": "Thiet ke UI",
                "quantity": 1,
                "unit_price": 20000000,
                "amount": 20000000,
            }
        ],
    },
    "terms": {"payment_terms": "50% tam ung, 50% khi ban giao"},
    "notes": "Khach cung cap logo",
}

# Shape nội bộ của AI — /proposals/ai-generate lưu thẳng output của model.
AI_CONTENT = {
    "project_overview": "Website ban hang tich hop VNPay",
    "scope_of_work": ["Thiet ke UI", "Lap trinh frontend"],
    "deliverables": ["Source code", "Tai lieu"],
    "timeline": "2 thang",
    "pricing": "50.000.000 VND",
    "payment_terms": "50% tam ung",
    "assumptions": "Khach cung cap logo",
}


class TestBuildProposalDocument:
    def test_ai_shape_still_works(self):
        """Shape AI vốn đã chạy được — không được làm hỏng nó.  #Huynh"""
        doc = build_proposal_document(AI_CONTENT, **META)
        assert doc.project_overview == "Website ban hang tich hop VNPay"
        assert doc.scope_of_work == ["Thiet ke UI", "Lap trinh frontend"]
        assert doc.deliverables == ["Source code", "Tai lieu"]
        assert doc.timeline == "2 thang"
        assert doc.pricing == "50.000.000 VND"
        assert doc.payment_terms == "50% tam ung"

    def test_contract_dto_shape_works(self):
        """Đúng ca đã gây 500: frontend lưu shape của hợp đồng, BE không đọc nổi.  #Huynh"""
        doc = build_proposal_document(DTO_CONTENT, **META)

        # executive_summary (hợp đồng) đóng vai trò project_overview (AI)
        assert doc.project_overview == "Website ban hang tich hop VNPay"
        # scope_of_work là CHUỖI nhiều dòng ở shape hợp đồng, phải tách thành list
        assert doc.scope_of_work == [
            "Thiet ke UI",
            "Lap trinh frontend",
            "Tich hop thanh toan",
        ]
        # pricing là OBJECT ở shape hợp đồng → giờ dựng thành BẢNG hạng mục có cấu trúc
        # (`pricing_line_items` + `pricing_total`), để template PDF render bảng giống hệt
        # card trên màn hình. Chuỗi `pricing` để trống khi đã có bảng.  #Huynh
        assert doc.pricing_total == "50.000.000 VND"
        assert any(item.description == "Thiet ke UI" for item in doc.pricing_line_items)
        assert any(item.amount == "20.000.000 VND" for item in doc.pricing_line_items)
        # timeline cũng là object
        assert "2026-08-01" in doc.timeline
        assert "Ban giao thiet ke" in doc.timeline
        # payment_terms nằm lồng trong terms{}
        assert doc.payment_terms == "50% tam ung, 50% khi ban giao"
        # notes (hợp đồng) đóng vai trò assumptions (AI)
        assert doc.assumptions == "Khach cung cap logo"

    def test_missing_keys_do_not_crash(self):
        """Thiếu khoá thì để trống, KHÔNG được nổ KeyError → 500 như bản cũ.  #Huynh"""
        doc = build_proposal_document({}, **META)
        assert doc.project_overview == ""
        assert doc.scope_of_work == []
        assert doc.deliverables == []
        assert doc.pricing == ""

    def test_none_content_does_not_crash(self):
        doc = build_proposal_document(None, **META)  # type: ignore[arg-type]
        assert doc.project_overview == ""

    def test_deliverables_absent_in_contract_shape(self):
        """Shape hợp đồng KHÔNG có `deliverables` — phải ra list rỗng, không nổ.  #Huynh"""
        doc = build_proposal_document(DTO_CONTENT, **META)
        assert doc.deliverables == []


class TestPricingItemsOverride:
    """Freelancer sửa danh sách hạng mục ở mục 7 → `pricing_items` (chỉ nhãn) chia đều giá chốt."""

    def test_override_splits_total_equally_and_sums_exact(self):
        content = {
            "pricing_detail": {"final_price": 200_000_000, "suggested": 180_000_000},
            "pricing_items": ["Thiet ke UI", "Lap trinh", "Kiem thu"],
        }
        doc = build_proposal_document(content, **META)
        assert [i.description for i in doc.pricing_line_items] == [
            "Thiet ke UI",
            "Lap trinh",
            "Kiem thu",
        ]
        assert doc.pricing_total == "200.000.000 VND"
        # Tổng các dòng phải cộng ĐÚNG bằng giá chốt (dòng cuối gánh phần lẻ).
        nums = [int(i.amount.replace(".", "").replace(" VND", "")) for i in doc.pricing_line_items]
        assert sum(nums) == 200_000_000

    def test_override_ignored_when_no_price(self):
        # Chưa có giá → không dựng được bảng override, rơi về hành vi cũ (không nổ).
        doc = build_proposal_document({"pricing_items": ["A", "B"]}, **META)
        assert doc.pricing_line_items == []

    def test_empty_override_falls_back_to_pricing_detail(self):
        content = {**DTO_CONTENT, "pricing_items": []}
        doc = build_proposal_document(content, **META)
        # Override rỗng → dùng bảng cũ (pricing_detail/DTO), giữ nguyên hành vi.
        assert any(item.description == "Thiet ke UI" for item in doc.pricing_line_items)


class TestPricingItemsWithAmounts:
    """Dạng MỚI ``[{"label", "amount"}]`` — freelancer tự gõ tiền từng dòng.

    Vì sao có dạng này: panel bên trái màn review hiện số tiền chia đều, nhưng đó chỉ là con
    số FE tự tính để hiển thị, không được gửi đi. Chốt giá mà chưa sửa nhãn thì panel hiện
    "125tr × 4" trong khi tờ báo giá vẫn giữ tỷ lệ bộ định giá (200/150/75/75) — hai bên nói
    hai kiểu. Cho gõ tiền thẳng thì cái freelancer thấy chính là cái khách nhận.  #Huynh
    """

    def test_uses_typed_amounts_verbatim(self):
        content = {
            "pricing_detail": {"final_price": 500_000_000, "suggested": 500_000_000},
            "pricing_items": [
                {"label": "Phat trien backend", "amount": 200_000_000},
                {"label": "Phat trien frontend", "amount": 150_000_000},
                {"label": "Kiem thu", "amount": 150_000_000},
            ],
        }
        doc = build_proposal_document(content, **META)

        amounts = [
            int(i.amount.replace(".", "").replace(" VND", "")) for i in doc.pricing_line_items
        ]
        # DÙNG THẲNG số freelancer gõ, KHÔNG chia đều lại.
        assert amounts == [200_000_000, 150_000_000, 150_000_000]
        assert doc.pricing_total == "500.000.000 VND"

    def test_total_follows_items_not_agreed_price(self):
        """Tổng in ra = tổng các dòng, kể cả khi lệch giá chào.

        Tầng render vẽ TRUNG THỰC thứ đang có để freelancer nhìn thấy chỗ lệch mà sửa; chặn
        gửi là việc của `ProposalsService.transition_status`.  #Huynh
        """
        content = {
            "pricing_detail": {"final_price": 500_000_000, "suggested": 500_000_000},
            "pricing_items": [{"label": "A", "amount": 100_000_000}],
        }
        doc = build_proposal_document(content, **META)
        assert doc.pricing_total == "100.000.000 VND"

    def test_missing_amount_becomes_zero_row_not_dropped(self):
        """Thiếu tiền → dòng 0đ, KHÔNG biến mất.

        Mất hẳn một hạng mục khỏi báo giá gửi khách nguy hiểm hơn nhiều so với một dòng 0đ
        mà freelancer nhìn thấy ngay.  #Huynh
        """
        content = {
            "pricing_detail": {"final_price": 100_000_000},
            "pricing_items": [
                {"label": "Co tien", "amount": 100_000_000},
                {"label": "Thieu tien"},
            ],
        }
        doc = build_proposal_document(content, **META)
        assert [i.description for i in doc.pricing_line_items] == ["Co tien", "Thieu tien"]
        assert doc.pricing_line_items[1].amount.startswith("0")

    def test_mixed_shapes_fall_back_to_label_only(self):
        """Nửa dict nửa chuỗi → về dạng cũ, không lắp ghép bảng từ hai nguồn."""
        content = {
            "pricing_detail": {"final_price": 200_000_000},
            "pricing_items": [{"label": "A", "amount": 150_000_000}, "B"],
        }
        doc = build_proposal_document(content, **META)
        nums = [int(i.amount.replace(".", "").replace(" VND", "")) for i in doc.pricing_line_items]
        assert sum(nums) == 200_000_000  # chia đều theo giá chốt, không dùng 150tr đã gõ
