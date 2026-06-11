import json
import os

from google import genai

from dotenv import load_dotenv

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GOOGLE_API_KEY")
)


class LeadQualifierService:

    @staticmethod
    def clean_json_response(text: str) -> str:
        text = text.strip()

        text = text.replace("```json", "")
        text = text.replace("```", "")

        return text.strip()

    @staticmethod
    def qualify(inquiry_text: str):

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
            model="gemini-2.5-flash",
            contents=full_prompt,
        )

        cleaned = LeadQualifierService.clean_json_response(
            response.text
        )

        return json.loads(cleaned)