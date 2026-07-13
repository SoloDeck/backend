import json
from pathlib import Path

from groq import Groq

from src.ai.shared.json_output import extract_json_object

from ..schemas.proposal_content import ProposalContent
from ..schemas.proposal_generation_input import ProposalGenerationInput


class ProposalGenerationService:

    def __init__(self, client: Groq):
        self.client = client

    def _load_prompt(self) -> str:
        prompt_path = Path(__file__).parent.parent / "prompts" / "prompts.txt"
        return prompt_path.read_text(encoding="utf-8")

    # _clean_response() cũ chỉ cắt fence khi CẢ chuỗi bắt đầu bằng ``` — cùng bug với
    # lead_qualifier. Đã thay bằng extract_json_object() dùng chung.  #Huynh

    def generate(self, request: ProposalGenerationInput) -> ProposalContent:

        prompt_template = self._load_prompt()

        prompt = prompt_template + "\n\n" + f"""
Project Information

Client Name:
{request.client_name}

Company Name:
{request.company_name}

Project Type:
{request.project_type}

Project Description:
{request.project_description}

Estimated Scope:
{request.estimated_scope}

Budget:
{request.budget}

Urgency:
{request.urgency}

Service Category:
{request.service_category}

Pricing Tier:
{request.pricing_tier}
"""

        response = self.client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=0.2,
            # Buộc model trả JSON thuần. Thiếu cờ này, llama-4-scout bọc câu trả lời
            # trong văn bản và parser vỡ — đúng bug đã làm chết lead_qualifier.  #Huynh
            response_format={"type": "json_object"},
        )

        raw_response = response.choices[0].message.content or ""

        try:
            content = extract_json_object(raw_response)

        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Model did not return valid JSON:\n{raw_response}"
            ) from exc

        return ProposalContent(**content)
