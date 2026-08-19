import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class ProfessionalProfileDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skills: list[str] | None = None
    specialization: str | None = None
    default_hourly_rate: Decimal | None = None
    currency: str
    portfolio_url: str | None = None
    business_name: str | None = None


class PaymentInfoDTO(BaseModel):
    """Thông tin nhận tiền — in vào thư nhắc thanh toán (QR VietQR + chuyển khoản + MoMo)."""

    model_config = ConfigDict(from_attributes=True)

    bank_code: str | None = None
    bank_account_number: str | None = None
    bank_account_holder: str | None = None
    momo_phone_number: str | None = None
    bank_account_info: str | None = None


class ReminderDefaultsDTO(BaseModel):
    """Mặc định khi soạn lời nhắc — để mỗi lần soạn không phải gõ lại từ đầu."""

    model_config = ConfigDict(from_attributes=True)

    reminder_signature: str | None = None
    reminder_default_channel: str | None = None
    reminder_default_hour: int | None = None


class PreferencesDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    locale: str
    timezone: str
    notification_channel: str
    theme: str


def build_user_fields(obj: Any) -> dict[str, Any]:
    """Map a UserModel ORM instance onto the UserResponse field shape."""
    return {
        "id": obj.id,
        "email": obj.email,
        "full_name": obj.full_name,
        "role": obj.role,
        "status": obj.status,
        "phone": obj.phone,
        "avatar_url": obj.avatar_url,
        "bio": obj.bio,
        "profession": obj.profession,
        "professional_title": obj.professional_title,
        "cover_url": obj.cover_url,
        "brand_color": obj.brand_color,
        "profile_slug": obj.profile_slug,
        "intake_share_token": obj.intake_share_token,
        # CHỈ trả có/không, tuyệt đối không trả hash ra ngoài.
        "has_password": obj.hashed_password is not None,
        "professional_profile": obj,
        "preferences": obj,
        "payment_info": obj,
        "reminder_defaults": obj,
        "created_at": obj.created_at,
        "updated_at": obj.updated_at,
    }


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: str
    status: str
    phone: str | None
    avatar_url: str | None
    bio: str | None
    profession: str | None = None
    # Headline hiện trên trang chia sẻ; FE cần đọc lại được để form Cài đặt hồ sơ hiển thị
    # đúng giá trị đang lưu sau khi tải lại trang. Ba trường diện mạo bên dưới cũng vậy —
    # thiếu chúng thì bấm F5 xong ảnh bìa và màu đã chọn biến mất khỏi màn cấu hình.
    professional_title: str | None = None
    cover_url: str | None = None
    brand_color: str | None = None
    profile_slug: str | None = None
    intake_share_token: str | None
    # Tài khoản này đã có mật khẩu chưa.
    #
    # Tài khoản tạo bằng đăng nhập Google có `hashed_password = NULL`
    # (`auth/service.py`), nên màn Bảo mật phải hiện form KHÁC: "Thêm mật khẩu" (2 ô)
    # thay vì "Đổi mật khẩu" (3 ô). Không có trường này thì frontend không cách nào biết,
    # và người dùng Google bị kẹt vĩnh viễn trước một ô "Mật khẩu hiện tại" mà họ chưa
    # từng có.
    #
    # Đây là điều kiện của TÀI KHOẢN, không phải của phiên đăng nhập: người đã có mật khẩu
    # rồi mới gắn thêm Google (`auth/service.py` nhánh nối theo email) vẫn phải nhập mật
    # khẩu cũ, kể cả hôm nay họ vào bằng Google.  #Huynh
    has_password: bool = False
    professional_profile: ProfessionalProfileDTO
    preferences: PreferencesDTO
    payment_info: PaymentInfoDTO
    reminder_defaults: ReminderDefaultsDTO
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _nest_profile_and_preferences(cls, obj: Any) -> Any:
        if isinstance(obj, dict):
            return obj
        return build_user_fields(obj)


class MessageResponse(BaseModel):
    detail: str
