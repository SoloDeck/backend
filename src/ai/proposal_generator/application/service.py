import json
from pathlib import Path

from google import genai

from ..schemas.ProposalContent import ProposalContent
from ..schemas.ProposalGenerationInput import ProposalGenerationInput


class ProposalGenerationService:

    def __init__(self, client: genai.Client):
        self.client = client

    def _load_prompt(self) -> str:
        prompt_path = (
            Path(__file__).parent.parent
            / "prompts"
            / "prompts.txt"
        )

        return prompt_path.read_text(encoding="utf-8")

    def _clean_response(self, text: str) -> str:
        """
        Remove markdown code fences if Gemini returns:

        ```json
        {...}
        ```
        """

        text = text.strip()

        if text.startswith("```json"):
            text = text.removeprefix("```json").strip()

        elif text.startswith("```"):
            text = text.removeprefix("```").strip()

        if text.endswith("```"):
            text = text.removesuffix("```").strip()

        return text

    def generate(
        self,
        request: ProposalGenerationInput
    ) -> ProposalContent:

        prompt_template = self._load_prompt()

        prompt = (
            prompt_template
            + "\n\n"
            + f"""
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
        )

        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        response_text = self._clean_response(
            response.text
        )

        try:
            content = json.loads(response_text)

        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Gemini did not return valid JSON:\n{response.text}"
            ) from exc

        return ProposalContent(**content)