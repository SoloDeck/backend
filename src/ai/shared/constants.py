"""
Shared constants used across the AI module.
"""

SUPPORTED_LLM_PROVIDERS: set[str] = {
    "groq",
    "gemini",
    "openai",
}

DEFAULT_LLM_PROVIDER = "groq"
