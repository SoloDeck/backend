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
        # pricing là OBJECT ở shape hợp đồng, phải dựng thành văn bản đọc được
        assert "50.000.000 VND" in doc.pricing
        assert "Thiet ke UI" in doc.pricing
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
