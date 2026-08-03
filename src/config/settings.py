from typing import Any, Literal

from pydantic import PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # A deploy pipeline that writes `VAR=${{ vars.VAR }}` unconditionally
        # produces a literal empty value whenever that CI variable isn't set
        # (e.g. `ZALO_MODE=`, `MOMO_REDIRECT_URL=`) — without this, pydantic
        # treats that as an explicit override and crashes Settings() at import
        # time (Literal fields) or silently reintroduces the momo redirect/ipn
        # collision (str fields), instead of falling back to the field default.
        env_ignore_empty=True,
    )

    # -----------------------------------------------------------------------
    # Application
    # -----------------------------------------------------------------------
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    secret_key: str = "change-me"

    # -----------------------------------------------------------------------
    # Logging
    # -----------------------------------------------------------------------
    # Override the per-environment default level (DEBUG in dev, INFO otherwise).
    # Production is clamped to INFO minimum regardless of this value.
    log_level: str | None = None
    # Override the per-environment default format: "console" (pretty) or "json".
    log_format: str | None = None
    # Service name stamped on every structured log entry.
    service_name: str = "solodesk-api"
    # Debug-only: log request/response bodies. Forced OFF in production.
    log_request_body: bool = False

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
    # Google Services
    # -----------------------------------------------------------------------
    gemini_api_key: str = ""  # For Gemini API or other Google services
    # Per-platform OAuth client IDs — the expected ID token audience is chosen
    # by the originating client platform (web / android / ios).
    google_web_client_id: str = ""
    google_android_client_id: str = ""
    google_ios_client_id: str = ""


    # -----------------------------------------------------------------------
    # Groq
    # -----------------------------------------------------------------------
    groq_api_key: str = ""

    # -----------------------------------------------------------------------
    # OpenAI
    # -----------------------------------------------------------------------
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_max_retries: int = 3
    openai_timeout: int = 60

    # -----------------------------------------------------------------------
    # Groq (lead qualifier)
    # -----------------------------------------------------------------------
    groq_api_key: str = ""

    # -----------------------------------------------------------------------
    # Stripe
    # -----------------------------------------------------------------------
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # -----------------------------------------------------------------------
    # MoMo (AIOv2 — https://developers.momo.vn/v2/#/docs/aiov2)
    # Defaults are MoMo's published sandbox test-merchant credentials
    # (test-payment.momo.vn) — fine for this university project's sandbox
    # testing, but overridable via env if a personal test merchant is used.
    # -----------------------------------------------------------------------
    momo_partner_code: str = "MOMO"
    momo_access_key: str = "F8BBA842ECF85"
    momo_secret_key: str = "K951B6PE1waDMi640xX08PD3vg6EkVlz"
    momo_partner_name: str = "SoloDesk"
    momo_store_id: str = "SoloDeskStore"
    momo_endpoint: str = "https://test-payment.momo.vn/v2/gateway/api/create"
    momo_request_type: str = "captureWallet"
    momo_lang: str = "vi"
    momo_ipn_url: str = "https://api.solodesk.space/api/v1/payments/webhooks/momo"
    # Browser landing target after MoMo's checkout page (success AND
    # cancel/resultCode!=0) — GET-reachable, unlike momo_ipn_url which is the
    # POST-only server-to-server IPN webhook (see public_router.py). Must always
    # be configured and must never equal momo_ipn_url — MomoClient enforces this
    # at request time (see integrations/momo/client.py _resolve_redirect_url).
    # NOTE for deploy: if a real .env sets MOMO_REDIRECT_URL="" explicitly it
    # will override this default and checkout will start raising a loud
    # PaymentGatewayError instead of silently producing the old 405 bug — that
    # env var needs a real value (or to be unset) in every deployed environment.
    momo_redirect_url: str = "https://api.solodesk.space/api/v1/payments/webhooks/momo/result"
    momo_timeout_seconds: float = 15.0

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
    smtp_tls: bool = False  # True → SMTP_SSL (port 465)
    smtp_starttls: bool = False  # True → STARTTLS after connect (port 587)

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

    # -----------------------------------------------------------------------
    # Frontend
    # -----------------------------------------------------------------------
    # Nơi backend chuyển hướng người dùng về sau các luồng OAuth ngoài (Zalo…).
    frontend_url: str = "http://localhost:5173"

    # -----------------------------------------------------------------------
    # Zalo Official Account
    # -----------------------------------------------------------------------
    # app_id/app_secret là của MỘT app SoloDesk trên Zalo Developers — nhiều OA của các
    # freelancer nối vào cùng app này; token của TỪNG OA lưu trên `users.zalo_oa_*`.
    # `zalo_mode`: "mock" (mặc định — chạy local/test, thành công tất định, KHÔNG gọi mạng)
    # hoặc "real" (gọi API Zalo thật; cần app thật + URL công khai cho callback/webhook).
    zalo_mode: Literal["mock", "real"] = "mock"
    zalo_app_id: str = ""
    zalo_app_secret: str = ""
    # Redirect URI đã khai ở Zalo Developers — PHẢI là URL công khai khớp từng ký tự.
    zalo_oauth_redirect_uri: str = ""
    # Bí mật để xác thực chữ ký webhook Zalo (đối chiếu header `X-ZEvent-Signature`).
    zalo_webhook_secret: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()  # type: ignore[call-arg]
