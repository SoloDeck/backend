import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.modules.intake_form.professions import is_valid_profession

# Ảnh lưu dạng data URL base64 nên độ dài phải chặn Ở ĐÂY — cột là Text, không tự giới hạn.
# Không có chốt này thì một request curl nhét chuỗi 50MB vào là mọi GET /users/me của tài
# khoản đó chết vĩnh viễn. 1.5 triệu ký tự ≈ 1.1MB nhị phân, dư cho ảnh đã nén ở client.
_IMAGE_MAX_CHARS = 1_500_000

_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

# 3–32 ký tự, chỉ chữ thường/số/gạch ngang, không mở đầu hay kết thúc bằng gạch.
_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,30})[a-z0-9]$")

# Slug thành đường dẫn gốc `/{slug}` nên phải tránh MỌI route gốc của frontend, cộng những
# tên hạ tầng hay bị trỏ tới. Thiếu một cái là có người đăng ký chiếm được /login.  #Huynh
_RESERVED_SLUGS = frozenset(
    {
        "admin", "api", "app", "assets", "static", "www", "cdn", "mail", "smtp", "ftp",
        "bieu-mau", "ho-so", "intake", "clients", "deals", "login", "register",
        "onboarding", "home", "forgot-password", "reset-password", "settings",
        "dashboard", "profile", "account", "billing", "help", "support", "about",
        "terms", "privacy", "blog", "docs", "status", "health", "zalo", "solodesk",
    }
)


def _safe_image_url(v: str | None) -> str | None:
    """Chỉ nhận dữ liệu ảnh hoặc link https — chặn javascript: và các lược đồ lạ.

    Giá trị này đi thẳng vào thuộc tính src của thẻ img trên trang ai cũng mở được. Dùng
    chung cho `avatar_url` lẫn `cover_url`: hai trường hiện cạnh nhau trên cùng một trang,
    để mỗi trường một luật là kiểu gì cũng có ngày lệch.  #Huynh
    """
    if v is None or not v.strip():
        return None
    v = v.strip()
    if not (v.startswith("data:image/") or v.startswith("https://")):
        raise ValueError("Ảnh phải là dữ liệu ảnh hoặc đường dẫn https")
    return v


class UpdateUserRequest(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    # Cùng chốt chặn như `FreelancerProfileUpdateRequest`: đường này cũng ghi avatar (màn
    # onboarding dùng nó), mà trước đây không có cả giới hạn độ dài lẫn kiểm lược đồ — tức
    # là đúng kịch bản nhét chuỗi 50MB mà chú thích ở đầu file viết ra để phòng.  #Huynh
    avatar_url: str | None = Field(default=None, max_length=_IMAGE_MAX_CHARS)
    bio: str | None = None

    @field_validator("avatar_url")
    @classmethod
    def _safe_avatar_url(cls, v: str | None) -> str | None:
        return _safe_image_url(v)


class FreelancerProfileUpdateRequest(BaseModel):
    professional_title: str | None = None
    bio: str | None = None
    skills: list[str] | None = None
    avatar_url: str | None = Field(default=None, max_length=_IMAGE_MAX_CHARS)
    portfolio_url: str | None = None
    # Slug nghề chuẩn hoá; validate qua seam của intake_form (None = bỏ chọn, vẫn hợp lệ).
    profession: str | None = None

    # --- Diện mạo trang công khai ---
    cover_url: str | None = Field(default=None, max_length=_IMAGE_MAX_CHARS)
    brand_color: str | None = None
    profile_slug: str | None = None

    # --- Nhận tiền: in vào thư nhắc thanh toán để khách biết chuyển vào đâu ---
    #
    # `bank_code` là mã BIN VietQR (ví dụ 970436 = Vietcombank), chọn từ danh sách chứ không
    # gõ tay — sai mã thì mã QR trỏ nhầm ngân hàng.  #Huynh
    bank_code: str | None = None
    bank_account_number: str | None = None
    bank_account_holder: str | None = None
    momo_phone_number: str | None = None
    bank_account_info: str | None = None

    # --- Mặc định khi soạn lời nhắc ---
    reminder_signature: str | None = None
    reminder_default_channel: Literal["email", "zalo", "in_app"] | None = None
    reminder_default_hour: int | None = Field(default=None, ge=0, le=23)

    @field_validator("profession")
    @classmethod
    def _valid_profession(cls, v: str | None) -> str | None:
        if not is_valid_profession(v):
            raise ValueError("Nghề không hợp lệ")
        return v

    @field_validator("brand_color")
    @classmethod
    def _valid_brand_color(cls, v: str | None) -> str | None:
        """Mã hex, hoặc rỗng để trả về màu mặc định.

        Nhánh chuỗi rỗng → None là BẮT BUỘC, không phải cho đẹp: màn Cài đặt gửi mọi trường
        trong MỘT lượt `await`, nên nếu người chưa chọn màu mà gửi "" bị 422 thì cả lượt lưu
        hồ sơ hỏng theo — đúng vết xe đổ của lỗi số điện thoại trùng.  #Huynh
        """
        if v is None or not v.strip():
            return None
        v = v.strip()
        if not _HEX_COLOR.match(v):
            raise ValueError("Màu chủ đạo phải là mã hex, ví dụ #5B3DF5")
        return v.lower()

    @field_validator("avatar_url", "cover_url")
    @classmethod
    def _safe_image_urls(cls, v: str | None) -> str | None:
        return _safe_image_url(v)

    @field_validator("profile_slug")
    @classmethod
    def _valid_profile_slug(cls, v: str | None) -> str | None:
        """Tên đường dẫn riêng: 3–32 ký tự thường, số, gạch ngang. Rỗng = bỏ tên."""
        if v is None or not v.strip():
            return None
        v = v.strip().lower()
        if not _SLUG.match(v):
            raise ValueError(
                "Tên đường dẫn chỉ gồm chữ thường, số và dấu gạch ngang, "
                "dài 3–32 ký tự, không bắt đầu hay kết thúc bằng gạch ngang"
            )
        if v in _RESERVED_SLUGS:
            raise ValueError(f"'{v}' là tên dành riêng cho hệ thống, bạn chọn tên khác nhé")
        return v


class UpdateProfessionalProfileRequest(BaseModel):
    skills: list[str] | None = None
    specialization: str | None = None
    default_hourly_rate: Decimal | None = None
    currency: str | None = None
    portfolio_url: str | None = None
    business_name: str | None = None


class UpdatePreferencesRequest(BaseModel):
    locale: str | None = None
    timezone: str | None = None
    notification_channel: Literal["email", "in_app", "both", "zalo"] | None = None
    theme: Literal["light", "dark"] | None = None


class ChangePasswordRequest(BaseModel):
    # Tuỳ chọn vì tài khoản đăng nhập bằng Google CHƯA HỀ có mật khẩu — không có gì để gửi.
    #
    # ⚠️ Tuỳ chọn ở ĐÂY không có nghĩa là tuỳ chọn ở mọi nơi: `UsersService.change_password`
    # vẫn BẮT BUỘC trường này với tài khoản đã có mật khẩu. Bỏ chốt chặn bên đó là ai cướp
    # được phiên cũng đổi được mật khẩu người khác mà không cần biết mật khẩu cũ.  #Huynh
    current_password: str | None = None
    new_password: str
