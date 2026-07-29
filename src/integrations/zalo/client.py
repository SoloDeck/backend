"""Client Zalo Official Account — bản THẬT (gọi API Zalo) + bản MOCK (test/local).

Tất cả đường ra Zalo đi qua interface ``ZaloOAClient`` để chỗ gọi (module ``zalo``, khâu gửi
nhắc) không phụ thuộc vào việc đang chạy thật hay mock. Chọn bản nào bằng ``settings.zalo_mode``:

- ``mock`` (mặc định): thành công tất định, KHÔNG chạm mạng — chạy được local + test xanh ngay cả
  khi CHƯA có app Zalo thật / URL công khai. `build_oauth_url` trỏ thẳng về callback của chính
  backend kèm ``code`` giả, nên toàn bộ luồng kết nối vẫn chạy trọn vẹn.
- ``real``: gọi API Zalo thật (OAuth v4 + OpenAPI v3). Cần app thật + redirect/webhook công khai.

Ký webhook (``verify_zalo_signature``) là toán tất định nên để hàm thuần, dùng chung cho cả hai
chế độ — không phụ thuộc client.  #Huynh
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlencode, urlparse

import httpx
import structlog

log = structlog.get_logger(__name__)

# Zalo OAuth v4 + OpenAPI v3 — điểm cuối chính thức.
_OAUTH_PERMISSION_URL = "https://oauth.zaloapp.com/v4/oa/permission"
_OAUTH_TOKEN_URL = "https://oauth.zaloapp.com/v4/oa/access_token"
_OA_MESSAGE_CS_URL = "https://openapi.zalo.me/v3.0/oa/message/cs"
_OA_GET_PROFILE_URL = "https://openapi.zalo.me/v2.0/oa/getoa"

# Mã lỗi Zalo coi là VĨNH VIỄN (thử lại vô ích): token hết hạn/không hợp lệ, thiếu quyền,
# người nhận ngoài cửa sổ tương tác 7 ngày, chưa quan tâm OA. Ngoài danh sách này (kể cả
# lỗi mạng/5xx) coi là TẠM để retry.
_PERMANENT_ZALO_ERRORS = frozenset({-201, -204, -211, -213, -216, -32, -240, -108, -109})

_TIMEOUT = httpx.Timeout(10.0)

# Domain hầm tạm (ngrok, cloudflare tunnel…). Zalo TỪ CHỐI chúng vì không xác thực được
# chủ sở hữu — đây chính là bức tường `-14003` đã chặn cả buổi thử hôm 24/07: URL backend
# sinh ra đúng 100%, app khai đúng, nhưng Zalo vẫn không nhận vì domain là hầm tạm.  #Huynh
_TUNNEL_DOMAIN_SUFFIXES = (
    ".ngrok-free.dev",
    ".ngrok-free.app",
    ".ngrok.io",
    ".ngrok.app",
    ".trycloudflare.com",
    ".loca.lt",
    ".serveo.net",
)

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"})


def unusable_redirect_reason(redirect_uri: str) -> str | None:
    """Vì sao ``redirect_uri`` này KHÔNG THỂ dùng ở chế độ ``real``? ``None`` = dùng được.

    Zalo đòi redirect URI là **domain công khai HTTPS** đã khai trong "Miền ứng dụng" và
    đã xác thực. Ba trường hợp dưới đây hỏng CHẮC CHẮN, biết trước mà không cần hỏi Zalo —
    nên chặn tại máy chủ, kèm câu giải thích đọc được.

    Vì sao đáng làm: khi cấu hình sai, Zalo chỉ trả một trang trắng ghi
    ``error_code=-14003``. Không nói domain nào sai, không nói sai ở đâu. Người gặp nó
    gần như luôn đi lần nhầm sang phần khai báo app, trong khi lỗi nằm ngay trong `.env`.

    KHÔNG cố đoán "domain này đã khai trong Miền ứng dụng chưa" — chỉ Zalo biết. Ở đây chỉ
    bắt những ca CHẮC CHẮN sai, không suy diễn thêm.  #Huynh
    """
    uri = (redirect_uri or "").strip()
    if not uri:
        return "chưa được đặt"

    parsed = urlparse(uri)
    if parsed.scheme != "https":
        return f"phải dùng https:// (đang là '{parsed.scheme or 'không có scheme'}')"

    host = (parsed.hostname or "").lower()
    if host in _LOCAL_HOSTS:
        return f"trỏ vào máy cục bộ ('{host}') — Zalo phải gọi được từ ngoài Internet"

    if any(host.endswith(suffix) for suffix in _TUNNEL_DOMAIN_SUFFIXES):
        return f"là domain hầm tạm ('{host}') — Zalo không chấp nhận, phải dùng domain thật"

    return None


class ZaloError(Exception):
    """Lỗi khi làm việc với Zalo OA. Câu chữ để NGƯỜI DÙNG đọc → viết tiếng Việt."""


class ZaloTransientError(ZaloError):
    """Có thể tự khỏi (mất mạng, Zalo 5xx) → đáng thử lại."""


class ZaloPermanentError(ZaloError):
    """Thử lại cũng vậy (token hỏng, thiếu quyền, ngoài cửa sổ 7 ngày) → báo ngay."""


@dataclass(frozen=True)
class ZaloToken:
    """Token của MỘT OA sau khi kết nối. ``expires_in`` tính bằng giây."""

    access_token: str
    refresh_token: str
    expires_in: int = 90000  # ~25 giờ, mặc định của Zalo OA


# ---------------------------------------------------------------------------------
# PKCE + chữ ký webhook — hàm thuần, không phụ thuộc chế độ
# ---------------------------------------------------------------------------------


def generate_code_verifier() -> str:
    """Chuỗi ngẫu nhiên PKCE (RFC 7636) — giữ ở phía server giữa connect-url và callback."""
    return secrets.token_urlsafe(48)


def code_challenge_for(verifier: str) -> str:
    """``BASE64URL(SHA256(verifier))`` không đệm — phương thức S256 chuẩn OAuth PKCE."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def verify_zalo_signature(
    *, app_id: str, oa_secret: str, raw_body: bytes, timestamp: str, provided_mac: str
) -> bool:
    """Đối chiếu chữ ký webhook Zalo: ``mac = SHA256(appId + data + timestamp + OASecretKey)``.

    ``data`` là THÂN request thô (bytes nguyên bản) — không phải bản đã parse rồi serialize lại,
    vì thứ tự khoá/khoảng trắng đổi là chữ ký lệch. So sánh hằng-thời-gian để khỏi lộ qua timing.
    """
    if not (app_id and oa_secret and provided_mac):
        return False
    expected = hashlib.sha256(
        app_id.encode() + raw_body + timestamp.encode() + oa_secret.encode()
    ).hexdigest()
    return secrets.compare_digest(expected, provided_mac.strip().lower())


# ---------------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------------


@runtime_checkable
class ZaloOAClient(Protocol):
    def build_oauth_url(self, *, state: str, code_challenge: str) -> str:
        """URL cấp quyền để chuyển hướng freelancer sang Zalo (hoặc callback giả ở mock)."""
        ...

    async def exchange_code(self, *, code: str, code_verifier: str) -> ZaloToken: ...

    async def refresh(self, *, refresh_token: str) -> ZaloToken: ...

    async def get_oa_id(self, *, access_token: str) -> str:
        """Id của OA vừa kết nối (lưu vào ``users.zalo_oa_app_id``)."""
        ...

    async def send_cs_message(self, *, access_token: str, user_id: str, text: str) -> None:
        """Gửi tin CS tới ``user_id`` (follower OA). Lỗi → Zalo{Transient,Permanent}Error."""
        ...


# ---------------------------------------------------------------------------------
# Bản THẬT
# ---------------------------------------------------------------------------------


@dataclass
class RealZaloOAClient:
    app_id: str
    app_secret: str
    redirect_uri: str

    def build_oauth_url(self, *, state: str, code_challenge: str) -> str:
        query = urlencode(
            {
                "app_id": self.app_id,
                "redirect_uri": self.redirect_uri,
                "code_challenge": code_challenge,
                "state": state,
            }
        )
        return f"{_OAUTH_PERMISSION_URL}?{query}"

    async def exchange_code(self, *, code: str, code_verifier: str) -> ZaloToken:
        return await self._token_request(
            {
                "code": code,
                "app_id": self.app_id,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            }
        )

    async def refresh(self, *, refresh_token: str) -> ZaloToken:
        return await self._token_request(
            {
                "refresh_token": refresh_token,
                "app_id": self.app_id,
                "grant_type": "refresh_token",
            }
        )

    async def _token_request(self, form: dict[str, str]) -> ZaloToken:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
                resp = await http.post(
                    _OAUTH_TOKEN_URL,
                    data=form,
                    headers={
                        "secret_key": self.app_secret,
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
        except httpx.HTTPError as exc:  # mạng/timeout → tạm
            raise ZaloTransientError("Không kết nối được máy chủ Zalo. Sẽ thử lại.") from exc

        data = _safe_json(resp)
        access = data.get("access_token")
        if not access:
            # Zalo trả lỗi trong body (error/error_name) — code sai/hết hạn là vĩnh viễn.
            reason = data.get("error_name") or data.get("error") or resp.text
            raise ZaloPermanentError(f"Zalo từ chối cấp token: {reason}")
        return ZaloToken(
            access_token=access,
            refresh_token=data.get("refresh_token", ""),
            expires_in=int(data.get("expires_in") or 90000),
        )

    async def get_oa_id(self, *, access_token: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
                resp = await http.get(
                    _OA_GET_PROFILE_URL, headers={"access_token": access_token}
                )
        except httpx.HTTPError as exc:
            raise ZaloTransientError("Không lấy được thông tin OA từ Zalo. Sẽ thử lại.") from exc

        data = _safe_json(resp)
        oa_id = (data.get("data") or {}).get("oa_id")
        if not oa_id:
            raise ZaloPermanentError("Không đọc được oa_id từ Zalo.")
        return str(oa_id)

    async def send_cs_message(self, *, access_token: str, user_id: str, text: str) -> None:
        payload = {"recipient": {"user_id": user_id}, "message": {"text": text}}
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
                resp = await http.post(
                    _OA_MESSAGE_CS_URL,
                    json=payload,
                    headers={"access_token": access_token, "Content-Type": "application/json"},
                )
        except httpx.HTTPError as exc:
            raise ZaloTransientError("Không gửi được tin Zalo do lỗi mạng. Sẽ thử lại.") from exc

        if resp.status_code >= 500:
            raise ZaloTransientError("Máy chủ Zalo đang lỗi. Sẽ thử lại.")

        data = _safe_json(resp)
        error = int(data.get("error") or 0)
        if error != 0:
            message = data.get("message") or "Zalo từ chối gửi tin."
            if error in _PERMANENT_ZALO_ERRORS:
                raise ZaloPermanentError(f"Không gửi được Zalo: {message}")
            raise ZaloTransientError(f"Gửi Zalo tạm lỗi: {message}")


# ---------------------------------------------------------------------------------
# Bản MOCK
# ---------------------------------------------------------------------------------


@dataclass
class MockZaloOAClient:
    """Không chạm mạng. `build_oauth_url` trỏ về callback backend kèm ``code`` giả, nên bấm
    "Kết nối" ở chế độ mock vẫn chạy đủ: callback → exchange_code → lưu token → về FE.
    """

    redirect_uri: str
    sent: list[dict[str, str]] = field(default_factory=list)

    def build_oauth_url(self, *, state: str, code_challenge: str) -> str:
        base = self.redirect_uri or "http://localhost:8000/api/v1/zalo/callback"
        return f"{base}?{urlencode({'code': 'mock-auth-code', 'state': state})}"

    async def exchange_code(self, *, code: str, code_verifier: str) -> ZaloToken:
        return ZaloToken(
            access_token=f"mock-access-{secrets.token_hex(6)}",
            refresh_token=f"mock-refresh-{secrets.token_hex(6)}",
            expires_in=90000,
        )

    async def refresh(self, *, refresh_token: str) -> ZaloToken:
        return ZaloToken(
            access_token=f"mock-access-{secrets.token_hex(6)}",
            refresh_token=refresh_token,
            expires_in=90000,
        )

    async def get_oa_id(self, *, access_token: str) -> str:
        return "mock-oa-000"

    async def send_cs_message(self, *, access_token: str, user_id: str, text: str) -> None:
        # Ghi lại để test khẳng định "đã gọi gửi tới đúng người", không gửi đi đâu cả.
        self.sent.append({"user_id": user_id, "text": text})
        log.info("zalo.mock.send", user_id=user_id, chars=len(text))


# ---------------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------------


def get_zalo_client(settings: object) -> ZaloOAClient:
    """Chọn client theo ``settings.zalo_mode``. Mặc định/khi thiếu config → mock (an toàn)."""
    mode = getattr(settings, "zalo_mode", "mock")
    redirect_uri = getattr(settings, "zalo_oauth_redirect_uri", "") or ""
    if mode == "real":
        return RealZaloOAClient(
            app_id=getattr(settings, "zalo_app_id", ""),
            app_secret=getattr(settings, "zalo_app_secret", ""),
            redirect_uri=redirect_uri,
        )
    return MockZaloOAClient(redirect_uri=redirect_uri)


def _safe_json(resp: httpx.Response) -> dict[str, Any]:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}
