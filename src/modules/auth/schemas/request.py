from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("full_name")
    @classmethod
    def full_name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Full name must not be blank")
        return v.strip()


class LoginRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "admin@solodesk.dev",
                "password": "Admin@SoloDesk2025!",
            }
        }
    }

    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    # Optional so existing callers that only ever sent an access token keep working.
    # Without it, logout only blacklists the access token — the refresh token stays
    # valid until it naturally expires (up to 30 days), so anyone still holding it
    # (a cached mobile app, a captured token) can silently mint new access tokens
    # after the user thinks they've logged out. Pass it to actually close that gap.
    refresh_token: str | None = None


class PasswordResetRequestBody(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    # `email` la bat buoc, khong phai de tien tra cuu ma de RANG BUOC ma voi dung nguoi.
    # Truoc day than yeu cau chi co `otp`, nen truy van quet ca bang: bat ky ma nao con
    # song cua BAT KY ai cung mo khoa duoc, va ke tan cong chi can ban thu 000000 len
    # den khi trung mot ma bat ky trong hang tram ma dang song.  #Huynh
    email: EmailStr
    otp: str = Field(pattern=r"^\d{6}$", description="6-digit OTP sent via email")
    new_password: str = Field(min_length=8)


class GoogleAuthRequest(BaseModel):
    id_token: str
    platform: Literal["web", "android", "ios"]
