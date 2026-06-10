from typing import Any, Literal

from pydantic import PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -----------------------------------------------------------------------
    # Application
    # -----------------------------------------------------------------------
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    secret_key: str = "change-me"

    # -----------------------------------------------------------------------
    # Database
    # -----------------------------------------------------------------------
    database_url: PostgresDsn
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_echo: bool = False

    # -----------------------------------------------------------------------
    # Redis
    # -----------------------------------------------------------------------
    redis_url: RedisDsn = RedisDsn("redis://localhost:6379/0")

    # -----------------------------------------------------------------------
    # Celery
    # -----------------------------------------------------------------------
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # -----------------------------------------------------------------------
    # JWT
    # -----------------------------------------------------------------------
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30

    # -----------------------------------------------------------------------
    # Google OAuth
    # -----------------------------------------------------------------------
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""

    # -----------------------------------------------------------------------
    # OpenAI
    # -----------------------------------------------------------------------
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_max_retries: int = 3
    openai_timeout: int = 60

    # -----------------------------------------------------------------------
    # Stripe
    # -----------------------------------------------------------------------
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # -----------------------------------------------------------------------
    # Storage
    # -----------------------------------------------------------------------
    storage_endpoint: str = ""
    storage_bucket: str = "solodesk-uploads"
    storage_access_key: str = ""
    storage_secret_key: str = ""
    storage_region: str = "ap-southeast-1"

    # -----------------------------------------------------------------------
    # Email
    # -----------------------------------------------------------------------
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@solodesk.space"
    smtp_from_name: str = "SoloDesk"
    smtp_tls: bool = False

    # -----------------------------------------------------------------------
    # CORS
    # -----------------------------------------------------------------------
    cors_origins: Any = ["*"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            if not v.strip():
                return ["*"]
            if v.startswith("[") and v.endswith("]"):
                try:
                    import json
                    return json.loads(v)
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return v
        return ["*"]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()  # type: ignore[call-arg]
