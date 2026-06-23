from src.ai.proposal_generator.application.service import ProposalGenerationService


def test_clean_response_removes_json_fences():
    service = ProposalGenerationService(client=None)

    raw = """```json
{"a": 1}
```"""

    cleaned = service._clean_response(raw)

    assert cleaned == '{"a": 1}'