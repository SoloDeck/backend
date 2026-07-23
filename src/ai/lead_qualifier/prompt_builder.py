"""
Prompt builder for the Lead Qualification module.

Responsibilities
----------------
Builds the final prompt sent to the LLM by combining

- Base prompt instructions
- Qualification framework
- Retrieved profession knowledge
- Client inquiry
"""

from pathlib import Path


class LeadQualificationPromptBuilder:

    def __init__(self):

        self.prompt_template = self._load_prompt()

    def _load_prompt(self) -> str:

        prompt_path = (
            Path(__file__).parent
            / "prompts"
            / "prompts.txt"
        )

        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")

        return (
            "You are an expert freelance lead qualification assistant.\n"
            "Return ONLY valid JSON."
        )

    def build(
        self,
        *,
        profession: str | None,
        inquiry_context: str,
        retrieved_knowledge: str,
    ) -> str:
        """
        Creates the complete prompt for the LLM.
        """

        profession_text = profession or "Unknown"

        return f"""
{self.prompt_template}

====================================================
QUALIFICATION FRAMEWORK & KNOWLEDGE
====================================================

{retrieved_knowledge}

====================================================
CLIENT INFORMATION
====================================================

Profession:
{profession_text}

====================================================
CLIENT INQUIRY
====================================================

{inquiry_context}

====================================================
TASK
====================================================

Using ONLY the qualification framework and profession
knowledge above,

1. Identify the project type.
2. Extract all relevant qualification signals.
3. Evaluate budget.
4. Evaluate timeline.
5. Evaluate urgency.
6. Identify any missing information.
7. Identify any red flags.
8. Recommend next actions.
9. Estimate a reasonable price range.
10. Produce the required JSON output.

Return ONLY valid JSON.
""".strip()