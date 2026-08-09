"""
Shared constants used across the AI module.
"""

# ==========================================================
# Supported LLM providers
# ==========================================================

SUPPORTED_LLM_PROVIDERS: set[str] = {
    "groq",
    "gemini",
    "ollama",
}


# ==========================================================
# Supported models per provider
# ==========================================================

SUPPORTED_LLM_MODELS: dict[str, set[str]] = {
    "groq": {
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
    },
    "gemini": {
        "gemini-2.5-flash",
        "gemini-3.5-flash-lite",
    },
    "ollama": {
        "qwen3:4b",
    },
}


# ==========================================================
# Default configuration
# ==========================================================

DEFAULT_LLM_PROVIDER = "groq"

DEFAULT_LLM_MODEL = "llama-3.3-70b-versatile"