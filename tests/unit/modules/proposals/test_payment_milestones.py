"""Mốc thanh toán có cấu trúc trong báo giá (Phase B — Stage 1).

Kiểm 2 chỗ net-new: (1) ProposalContent ép kiểu `payment_milestones` từ output LLM thất
thường, (2) build_proposal_document trích milestones từ cả shape AI lẫn shape DTO.
"""

from src.ai.proposal_generator.schemas.proposal_content import ProposalContent
from src.ai.proposal_generator.schemas.proposal_document import default_payment_milestones
from src.modules.proposals.application.pdf_content import build_proposal_document
from src.modules.proposals.application.service import (
    _milestones_to_payloads,
    _payment_task_payloads,
)
from src.modules.tasks.application.service import PAYMENT_TASK_PREFIX

_BASE = {
    "project_overview": "Website ban hang",
    "scope_of_work": ["UI"],
    "deliverables": ["Source"],
    "timeline": "2 thang",
    "pricing": "",
    "payment_terms": "Coc 50% + 50%",
    "assumptions": "x",
}

_META = {
    "freelancer_name": "Huynh",
    "client_name": "Cong ty ABC",
    "company_name": "Cong ty ABC",
    "project_type": "Website",
    "proposal_date": "2026-07-27",
}


class TestProposalContentMilestones:
    def test_percent_string_and_alt_keys(self):
        c = ProposalContent(
            **_BASE,
            payment_milestones=[
                {"label": "Coc", "percent": "50%", "due": "Khi ky"},
                {"description": "Ban giao", "percentage": 50, "when": "Nghiem thu"},
            ],
        )
        assert [m.percent for m in c.payment_milestones] == [50, 50]
        assert c.payment_milestones[1].label == "Ban giao"
        assert c.payment_milestones[1].due == "Nghiem thu"

    def test_string_entry_and_malformed_skipped(self):
        c = ProposalContent(
            **_BASE,
            payment_milestones=["Thanh toan 1 lan", {"nolabel": 1}, 123],
        )
        assert [m.label for m in c.payment_milestones] == ["Thanh toan 1 lan"]
        assert c.payment_milestones[0].percent is None

    def test_missing_fills_default_schedule(self):
        # Không nêu mốc -> điền lịch CHUẨN 50/50 để luôn có mốc render + sinh task.  #Huynh
        milestones = ProposalContent(**_BASE).payment_milestones
        assert [m.percent for m in milestones] == [50, 50]

    def test_explicit_milestones_not_overridden_by_default(self):
        c = ProposalContent(
            **_BASE,
            payment_milestones=[{"label": "Trả 1 lần", "percent": 100, "due": "Khi bàn giao"}],
        )
        assert len(c.payment_milestones) == 1
        assert c.payment_milestones[0].percent == 100


class TestBuildProposalDocumentMilestones:
    def test_ai_shape(self):
        doc = build_proposal_document(
            {**_BASE, "payment_milestones": [{"label": "Coc", "percent": 50, "due": "Khi ky"}]},
            **_META,
        )
        assert len(doc.payment_milestones) == 1
        assert doc.payment_milestones[0].percent == 50

    def test_dto_payment_schedule(self):
        doc = build_proposal_document(
            {
                "executive_summary": "x",
                "terms": {
                    "payment_schedule": [
                        {"label": "Dot 1", "amount": "5.000.000 VND", "due": "Khi ky"}
                    ]
                },
            },
            **_META,
        )
        assert len(doc.payment_milestones) == 1
        assert doc.payment_milestones[0].amount == "5.000.000 VND"

    def test_no_milestones_ok(self):
        doc = build_proposal_document({**_BASE}, **_META)
        assert doc.payment_milestones == []


class TestPaymentTaskPayloads:
    """Từ mốc thanh toán của báo giá → task "Thu tiền:" (Phase B — mục 8/9)."""

    def test_builds_one_task_per_milestone_with_prefix(self):
        payloads = _payment_task_payloads(
            {
                "payment_milestones": [
                    {"label": "Đặt cọc khi ký", "percent": 50, "due": "Khi ký hợp đồng"},
                    {"label": "Bàn giao", "percent": 50, "due": "Khi nghiệm thu"},
                ]
            }
        )
        assert len(payloads) == 2
        assert all(p.title.startswith(PAYMENT_TASK_PREFIX) for p in payloads)
        assert payloads[0].title == "Thu tiền: Đặt cọc khi ký"
        assert "50%" in payloads[0].description
        assert "Khi ký hợp đồng" in payloads[0].description

    def test_amount_milestone_without_percent(self):
        payloads = _payment_task_payloads(
            {"payment_milestones": [{"label": "Đợt 1", "amount": "5.000.000 VND"}]}
        )
        assert payloads[0].title == "Thu tiền: Đợt 1"
        assert "5.000.000 VND" in payloads[0].description

    def test_no_milestones_no_tasks(self):
        assert _payment_task_payloads({}) == []
        assert _payment_task_payloads({"payment_milestones": []}) == []

    def test_default_schedule_maps_to_two_payment_tasks(self):
        # Fallback khi báo giá không có mốc: lịch chuẩn 50/50 -> 2 task "Thu tiền:".
        payloads = _milestones_to_payloads(default_payment_milestones())
        assert len(payloads) == 2
        assert all(p.title.startswith(PAYMENT_TASK_PREFIX) for p in payloads)
        assert "50%" in payloads[0].description
