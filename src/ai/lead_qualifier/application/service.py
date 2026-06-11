import json
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


class LeadQualifierService:
    """
    AI service wrapper for lead qualification.
    Client is lazily initialized to avoid CI import failures.
    """

    _client = None  # singleton cache

    # ------------------------------------------------------------------
    # Client initialization (lazy)
    # ------------------------------------------------------------------

    @classmethod
    def _get_client(cls):
        if cls._client is not None:
            return cls._client

        from google import genai

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY is not set. Required for LeadQualifierService."
            )

        cls._client = genai.Client(api_key=api_key)
        return cls._client

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def clean_json_response(text: str) -> str:
        text = text.strip()
        text = text.replace("```json", "")
        text = text.replace("```", "")
        return text.strip()

    # ------------------------------------------------------------------
    # Main logic
    # ------------------------------------------------------------------

    @classmethod
    def qualify(cls, inquiry_text: str):
        client = cls._get_client()

        prompt_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "prompts",
            "prompt.txt"
        )

        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt = f.read()

        full_prompt = f"""
{prompt}

Client Inquiry:

{inquiry_text}
"""

        response = client.models.generate_content(
            # model="gemma-4-26b-a4b-it",
            model="gemini-2.5-flash",
            contents=full_prompt,
        )

        cleaned = cls.clean_json_response(response.text)

        return json.loads(cleaned)