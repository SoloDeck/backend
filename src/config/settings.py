from typing import Any, ClassVar, Literal

from pydantic import PostgresDsn, RedisDsn, field_validator, model_validator
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
    # Ollama
    # -----------------------------------------------------------------------
    ollama_base_url: str = "http://localhost:11434"

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
    # Khoảng số tiền MoMo nhận cho MỘT giao dịch (amount kiểu Long, 1.000đ–50tr):
    # https://developers.momo.vn/v3/docs/payment/api/wallet/onetime/
    #
    # Gửi ra ngoài khoảng này MoMo trả HTTP 400 — KHÔNG phải một từ chối nghiệp vụ có
    # `resultCode` để đọc. Đó là lý do một gói giá 200đ từng hiện ra thành "Could not
    # reach MoMo": lỗi 400 rơi vào nhánh bắt lỗi mạng của client.
    #
    # Để ở settings thay vì hằng số vì đây là hạn mức của MoMo theo hợp đồng merchant,
    # không phải luật kinh doanh của SoloDesk — merchant thật có thể được nâng trần, và
    # lúc đó chỉ cần sửa env. Mặc định phải khớp hằng cùng tên trong
    # integrations/momo/client.py (bản đó phục vụ MockMomoClient và test).
    momo_min_amount: int = 1_000
    momo_max_amount: int = 50_000_000

    # -----------------------------------------------------------------------
    # ZaloPay (Open API v2 — https://docs.zalopay.vn/docs/specs/order-create/)
    # Defaults are ZaloPay's own published sandbox test app, committed in their
    # github.com/zalopay-samples/test-apps repo — same posture as the MoMo block
    # above: fine for this university project's sandbox, overridable via env.
    #
    # TWO keys, and they are NOT interchangeable: key1 signs our outbound
    # create-order request, key2 verifies ZaloPay's inbound callback. Swapping
    # them makes every real payment fail signature verification.
    # -----------------------------------------------------------------------
    zalopay_app_id: str = "2554"
    zalopay_key1: str = "sdngKKJmqEMzvh5QQcdD2A9XBSKUNaYn"
    zalopay_key2: str = "trMrHtvjo6myautxDUiAcYsVtaeQ8nhf"
    zalopay_app_user: str = "solodesk_user"
    zalopay_endpoint: str = "https://sb-openapi.zalopay.vn/v2/create"
    zalopay_query_endpoint: str = "https://sb-openapi.zalopay.vn/v2/query"
    zalopay_callback_url: str = "https://api.solodesk.space/api/v1/payments/webhooks/zalopay"
    # Browser landing target after ZaloPay's checkout page. Same rule as
    # momo_redirect_url: must be configured and must never equal
    # zalopay_callback_url (the POST-only webhook) — ZaloPayClient enforces this
    # at request time. Note it travels inside embed_data, not as a top-level
    # parameter, because ZaloPay has no redirect field of its own.
    zalopay_redirect_url: str = "https://api.solodesk.space/api/v1/payments/webhooks/zalopay/result"
    zalopay_timeout_seconds: float = 15.0
    # Cận dưới 1.000đ là mức ZaloPay công bố cho giao dịch trên app. Cận trên để bằng
    # MoMo cho nhất quán giữa hai cổng — trần THẬT của một merchant nằm trong hợp đồng
    # chứ không phải hằng số công khai, nên để ở env cho môi trường thật chỉnh.
    # Mặc định phải khớp hằng cùng tên trong integrations/zalopay/client.py.
    zalopay_min_amount: int = 1_000
    zalopay_max_amount: int = 50_000_000

    # -----------------------------------------------------------------------
    # SePay (bank-reconciliation gateway) — https://docs.sepay.vn/
    #
    # Khac hai cong tren o cho co ban: SePay KHONG giu tien va khong co API tao
    # don. Tien vao thang tai khoan ngan hang cua chinh ta; SePay doc bien dong
    # so du roi ban webhook. Vi vay o day khong co endpoint/secret de goi di —
    # chi co so tai khoan de dung ma QR, va mot khoa de XAC THUC webhook di vao.
    #
    # KHONG co gia tri mac dinh nao la that. Khac hai cong tren (chung dung
    # sandbox cong khai cua nha cung cap), SePay khong co sandbox dung chung:
    # tai khoan ngan hang la tai khoan that cua mot nguoi that. De trong nghia la
    # checkout SePay bao loi ro rang thay vi lang le dung so tai khoan cua nguoi khac.
    # -----------------------------------------------------------------------
    sepay_webhook_api_key: str = ""
    sepay_bank_code: str = ""
    sepay_account_number: str = ""
    sepay_qr_base_url: str = "https://vietqr.app/img"
    # Chi de doi chieu khi debug: webhook duoc cau hinh MOT LAN tren dashboard SePay
    # chu khong gui kem tung don nhu MoMo/ZaloPay.
    sepay_callback_url: str = "https://api.solodesk.space/api/v1/payments/webhooks/sepay"
    sepay_min_amount: int = 1_000
    sepay_max_amount: int = 50_000_000

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
    # Hết giờ chờ cho MỘT lần gửi thư. `smtplib` mặc định KHÔNG có timeout, nên máy chủ
    # thư im lặng (nhà cung cấp chặn cổng 587, hoặc gói tin bị nuốt) là treo tới tận
    # timeout TCP của hệ điều hành — cỡ 2 phút — và giữ luôn một thread trong pool.
    #
    # 10 giây không phải số tuỳ tiện: axios của web bỏ cuộc ở 15 giây
    # (`web/src/configs/axios.ts`). Backend phải trả lời TRƯỚC mốc đó, không thì mọi lỗi
    # SMTP đều hiện thành "mất mạng" ở phía người dùng và cả phần phân loại lỗi bên dưới
    # thành vô dụng vì câu trả lời không bao giờ về kịp. Sửa số này thì phải xem lại số kia.
    #
    # Đo thật trên staging 04/08: một lần gửi qua Gmail mất 3,7–4,4 giây, nên 10 giây còn
    # dư gấp đôi cho lúc mạng chậm.  #Huynh
    smtp_timeout_seconds: float = 10.0

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

    # Giá trị mặc định của chính file này, cộng vài chuỗi mẫu hay bị chép từ tài liệu.
    # Khoá nào còn mang một trong các giá trị này nghĩa là biến môi trường CHƯA tới nơi.  #Huynh
    _GIA_TRI_MAU: ClassVar[frozenset[str]] = frozenset(
        {
            "change-me",
            "change-me-in-production-minimum-32-chars",
            "your-secret-key",
            "secret",
            # Khoá sandbox công khai — ai đọc tài liệu của cổng cũng có.
            "sdngKKJmqEMzvh5QQcdD2A9XBSKUNaYn",  # zalopay key1
            "trMrHtvjo6myautxDUiAcYsVtaeQ8nhf",  # zalopay key2
            "F8BBA842ECF85",  # momo access key
            "K951B6PE1waDMi640xX08PD3vg6EkVlz",  # momo secret key
        }
    )

    @model_validator(mode="after")
    def chan_khoa_mac_dinh(self) -> "Settings":
        """Không cho chạy staging/production bằng khoá bí mật mặc định.

        Vì sao phải chết ngay lúc khởi động thay vì ghi log cảnh báo: `env_ignore_empty=True`
        ở đầu file khiến một biến môi trường RỖNG (pipeline ghi `JWT_SECRET_KEY=` khi GitHub
        secret chưa đặt hoặc bị đổi tên) rơi êm về giá trị mặc định. Không có lỗi, không có
        log, API vẫn khởi động, mọi người vẫn đăng nhập bình thường — trong khi bất kỳ ai
        cũng tự ký được token `role: admin` bằng khoá `change-me` mà đọc và sửa dữ liệu của
        MỌI freelancer. Hỏng ồn ào lúc deploy còn hơn chạy êm với khoá ai cũng đoán ra.  #Huynh

        Hai mức khắt khe khác nhau, theo đúng thứ pipeline đang truyền được:

        * `secret_key` và `jwt_secret_key` — chặn ở CẢ staging lẫn production. `ci.yml` đã
          truyền sẵn hai biến này cho cả hai môi trường nên chỉ cần GitHub secret tồn tại.
        * Khoá cổng thanh toán — chỉ chặn ở production. `ci.yml` hiện KHÔNG truyền
          `ZALOPAY_KEY1/KEY2` cho môi trường nào, và `MOMO_SECRET_KEY` chỉ có ở khối
          production; chặn ở staging là staging chết ngay lần merge tới trong khi staging
          vốn chỉ cần cổng sandbox. Trước lần deploy production kế tiếp phải bổ sung hai
          dòng ZALOPAY_KEY1/KEY2 vào `ci.yml` và đặt secret tương ứng, nếu không job deploy
          sẽ đỏ ở đúng bước này.
        """
        if self.app_env == "development":
            return self

        thieu: list[str] = []

        for ten in ("secret_key", "jwt_secret_key"):
            gia_tri = getattr(self, ten)
            if gia_tri in self._GIA_TRI_MAU:
                thieu.append(f"{ten.upper()} còn là giá trị mặc định")
            elif len(gia_tri) < 32:
                thieu.append(f"{ten.upper()} ngắn hơn 32 ký tự (đang {len(gia_tri)})")

        if self.is_production:
            for ten in (
                "zalopay_key1",
                "zalopay_key2",
                "momo_access_key",
                "momo_secret_key",
            ):
                if getattr(self, ten) in self._GIA_TRI_MAU:
                    thieu.append(f"{ten.upper()} còn là khoá sandbox công khai")

        if thieu:
            raise ValueError(
                f"Cấu hình bí mật chưa sẵn sàng cho môi trường {self.app_env!r}: "
                + "; ".join(thieu)
                + ". Đặt các biến môi trường tương ứng rồi khởi động lại."
            )

        return self


settings = Settings()  # type: ignore[call-arg]
