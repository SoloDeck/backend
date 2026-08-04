from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.modules.freelancers.application.service import (
    all_category_slugs,
    is_valid_category,
)
from src.modules.intake_form.professions import is_valid_profession


class UpdateUserRequest(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    avatar_url: str | None = None
    bio: str | None = None


class FreelancerProfileUpdateRequest(BaseModel):
    professional_title: str | None = None
    bio: str | None = None
    skills: list[str] | None = None
    service_categories: list[str] | None = None
    avatar_url: str | None = None
    portfolio_url: str | None = None
    is_listed: bool | None = None
    # Slug nghề chuẩn hoá; validate qua seam của intake_form (None = bỏ chọn, vẫn hợp lệ).
    profession: str | None = None

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

    @field_validator("service_categories")
    @classmethod
    def _valid_service_categories(cls, v: list[str] | None) -> list[str] | None:
        """Chỉ nhận slug trong danh mục của danh bạ.

        Trước đây trường này là `list[str]` trần không kiểm gì: onboarding gửi chức danh
        tiếng Anh ("Web Developer"), backend trả 200, rồi bộ lọc danh bạ so khớp bằng
        slug nên chọn nhóm nào cũng ra rỗng — hỏng âm thầm, không ai thấy lỗi ở đâu.
        Chặn tại cửa thì dữ liệu trong bảng luôn lọc được.  #Huynh
        """
        if v is None:
            return None
        invalid = [c for c in v if not is_valid_category(c)]
        if invalid:
            raise ValueError(
                f"Nhóm dịch vụ không hợp lệ: {invalid}. Hợp lệ: {all_category_slugs()}"
            )
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
