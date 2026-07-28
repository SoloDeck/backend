from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

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
    current_password: str
    new_password: str
