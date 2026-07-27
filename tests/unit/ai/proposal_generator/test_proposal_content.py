"""Test schema ProposalContent — chịu được kiểu dữ liệu bất thường từ model.  #Huynh"""

from src.ai.proposal_generator.schemas.proposal_content import ProposalContent

BASE = {
    "project_overview": "Website ban hang",
    "scope_of_work": ["Thiet ke UI", "Lap trinh FE"],
    "deliverables": ["Source code", "Tai lieu"],
    "timeline": "2 thang",
    "pricing": "50.000.000 VND",
    "payment_terms": "50% tam ung",
    "assumptions": "Khach cung cap logo",
}


class TestProposalContentCoercion:
    def test_plain_shape_unchanged(self):
        c = ProposalContent(**BASE)
        assert c.pricing == "50.000.000 VND"
        assert c.scope_of_work == ["Thiet ke UI", "Lap trinh FE"]

    def test_pricing_as_dict_is_coerced(self):
        """Đúng ca đã làm endpoint 500: model trả `pricing` dạng object.

        Prompt yêu cầu chuỗi, nhưng llama-4-scout thỉnh thoảng trả object — cùng một
        request, lần được lần không. Trước đây pydantic ném ValidationError → 500.  #Huynh
        """
        c = ProposalContent(
            **{
                **BASE,
                "pricing": {
                    "total": "50.000.000 VND",
                    "breakdown": [{"item": "Thiet ke", "cost": "10.000.000 VND"}],
                },
            }
        )
        assert isinstance(c.pricing, str)
        assert "50.000.000 VND" in c.pricing

    def test_scope_as_string_becomes_list(self):
        c = ProposalContent(**{**BASE, "scope_of_work": "Thiet ke UI"})
        assert c.scope_of_work == ["Thiet ke UI"]

    def test_deliverables_as_dicts_are_flattened(self):
        c = ProposalContent(**{**BASE, "deliverables": [{"name": "Source code"}]})
        assert c.deliverables == ["name: Source code"]

    def test_none_becomes_empty(self):
        c = ProposalContent(**{**BASE, "assumptions": None})
        assert c.assumptions == ""
