import uuid
from decimal import Decimal
from typing import Any

from pydantic import AliasChoices, BaseModel, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from src.modules.deals.domain.value_objects.deal_stage import DealStage
from src.shared.types.length_limits import LengthLimitedModel

# Cột `deals.estimated_value` / `actual_value` là NUMERIC(15, 2): tối đa 13 chữ số trước dấu phẩy.
# Vượt thì Postgres ném NumericValueOutOfRangeError → HTTP 500, y như chuỗi dài hơn cột VARCHAR.
_MAX_MONEY = Decimal("9999999999999.99")
# Cùng con số, viết kiểu Việt Nam (chấm ngăn nghìn, phẩy thập phân) để đưa vào câu báo lỗi.
_MAX_MONEY_TEXT = f"{_MAX_MONEY:,.2f}".translate(str.maketrans(",.", ".,"))


# Mọi `max_length` ở đây ĐÚNG BẰNG độ dài cột tương ứng trong `infrastructure/database/models.py`
# (DealModel, DealIntakeModel, ClientModel) — test `test_request_length_limits.py` canh chỗ lệch.
# Trước đây các trường này không có giới hạn: gõ dài hơn cột là Postgres từ chối bằng
# StringDataRightTruncationError và API trả 500 "An unexpected error occurred" thay vì 422 kèm
# trường nào dài quá. Câu báo lỗi tiếng Việt do `LengthLimitedModel` lo, lấy tên từ `title`.  #Huynh
class DealRequest(LengthLimitedModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "client_id": "e1f881a5-fe2a-4f62-bcda-c0371077a924",
                "title": "Xay dung website ban hang",
                "stage": "new_lead",
                "source": "referral",
                "project_type": "E-commerce Website",
                "service_category": "Web Development",
                "pricing_tier": "standard",
                "estimated_value": 50000000,
                "currency": "VND",
                "desired_timeline": "2 thang",
                "notes": "Khach can website ban hang tich hop thanh toan VNPay va MOMO",
            }
        }
    }

    client_id: uuid.UUID
    title: str = Field(max_length=500, title="Tên yêu cầu")
    stage: str = "new_lead"
    source: str | None = None
    # ge=0: trước đây tạo được deal giá trị ÂM (-1.000.000 đ) và nó cộng luôn vào tổng
    # doanh thu trên bảng Kanban. API trả 201 vô tư.  #Huynh
    estimated_value: Decimal | None = Field(default=None, ge=0, title="Giá trị dự kiến")
    actual_value: Decimal | None = Field(default=None, ge=0, title="Giá trị thực tế")
    currency: str = Field(default="VND", max_length=3, title="Mã tiền tệ")
    notes: str | None = None
    desired_timeline: str | None = Field(default=None, max_length=255, title="Thời hạn khách nêu")
    # Ngân sách KHÁCH nêu, ghi lại sau khi hỏi được. Là chuỗi chứ không phải số vì khách hay
    # nói "50-80 triệu", "tầm 100 củ" — ép về số là mất đúng phần thông tin đáng giá.
    #
    # KHÁC `estimated_value` bên trên: đó là freelancer tự ước để tính doanh thu, và bị cấm
    # dùng để chấm điểm. Ô này là lời khách nên ĐƯỢC chấm.  #Huynh
    client_budget: str | None = Field(default=None, max_length=255, title="Ngân sách khách nêu")
    project_type: str | None = Field(default=None, max_length=200, title="Loại dự án")
    service_category: str | None = Field(default=None, max_length=200, title="Nhóm dịch vụ")
    pricing_tier: str | None = Field(default=None, max_length=100, title="Mức giá")
    # Profession-specific qualification
    profession: str | None = Field(default=None, max_length=100, title="Nghề")
    profession_fields: dict[str, Any] | None = None

    @field_validator("estimated_value", "actual_value")
    @classmethod
    def _khong_vuot_cot_tien(cls, value: Decimal | None, info: ValidationInfo) -> Decimal | None:
        """Chặn số quá lớn so với cột NUMERIC(15, 2) — cùng họ lỗi với chuỗi dài hơn cột."""
        if value is not None and value > _MAX_MONEY:
            field = cls.model_fields.get(info.field_name or "")
            raise PydanticCustomError(
                "decimal_too_large",
                "{label} quá lớn, tối đa {max_value}",
                {
                    "label": (field.title if field else None) or "Giá trị",
                    "max_value": _MAX_MONEY_TEXT,
                },
            )
        return value


class SaveQualificationRequest(BaseModel):
    """Body tuỳ chọn của `POST /deals/{id}/qualifications/save`.

    Mặc định `false` để đường gọi cũ (POST không body) vẫn chạy y như trước.
    """

    # Chốt ĐÚNG bản chấm này. Bỏ trống thì chốt bản mới nhất.
    #
    # Cần cho luồng "mở lại bản cũ ở tab Lịch sử rồi chốt": lúc đó bản đang xem KHÔNG phải
    # bản mới nhất. Không có nó thì freelancer buộc phải chấm lại — tốn một lượt AI cho một
    # kết quả đã có sẵn.
    qualification_id: uuid.UUID | None = None

    # Giao diện đã cảnh báo bản này chưa đủ 100 điểm và người dùng vẫn chọn chốt.
    gap_acknowledged: bool = False


class DealStageRequest(BaseModel):
    # Kiểu là DealStage (enum) chứ không phải str trần: giai đoạn rác ("khong_ton_tai")
    # trước đây lọt qua schema rồi mới bị service chặn, nên trả 409 CONFLICT — sai ngữ
    # nghĩa. 409 nghĩa là "xung đột trạng thái", còn đây là DỮ LIỆU KHÔNG HỢP LỆ → 422.
    # Để pydantic chặn ngay ở cửa, FastAPI tự trả 422 kèm danh sách giá trị hợp lệ.  #Huynh
    target_stage: DealStage = Field(validation_alias=AliasChoices("target_stage", "stage"))
    # Lý do dự án không thành công, chỉ dùng khi `target_stage = lost` (giai đoạn khác thì bỏ
    # qua). Không bắt buộc ở API để client cũ (app di động) không gửi vẫn chạy; web đòi nhập ở
    # hộp thoại.
    reason: str | None = Field(default=None, max_length=1000)

    @property
    def stage(self) -> str:
        return self.target_stage


class AddNoteRequest(BaseModel):
    description: str = Field(min_length=1)


class PublicIntakeRequest(LengthLimitedModel):
    """Body for the public (unauthenticated) lead intake form.

    Required fields are validated dynamically against the freelancer's form config.
    `name` is always required at the schema level (needed to create a client record).
    """

    name: str = Field(min_length=1, max_length=255, title="Họ tên")
    email: str | None = Field(default=None, max_length=255, title="Email")
    phone: str | None = Field(default=None, max_length=50, title="Số điện thoại")
    project_name: str | None = Field(default=None, max_length=500, title="Tên dự án")
    inquiry_text: str | None = Field(default=None, max_length=5000, title="Nội dung yêu cầu")
    estimated_budget: str | None = Field(default=None, max_length=255, title="Ngân sách")
    desired_timeline: str | None = Field(default=None, max_length=255, title="Thời gian mong muốn")
    # Số tệp khách SẮP tải lên qua `POST /intake/{token}/{intake_id}/attachments`.
    #
    # Chỉ dùng để quyết định THỜI ĐIỂM gửi thư báo deal mới: có tệp thì hoãn một nhịp cho
    # tệp kịp lên rồi mới đếm, không thì gửi ngay. Giá trị do client gửi nên KHÔNG được
    # dùng làm dữ liệu — số tệp in trong thư luôn đếm lại từ DB.  #Huynh
    attachment_count: int = Field(default=0, ge=0, le=10)
    # Profession selected by the client. Đi thẳng vào `deals.profession` (VARCHAR(100)): thiếu
    # giới hạn ở đây thì một request công khai (KHÔNG cần đăng nhập) gửi chuỗi dài là 500.
    profession: str | None = Field(default=None, max_length=100, title="Nghề")
    # Profession-specific intake answers (5 questions for the selected profession)
    profession_fields: dict[str, Any] | None = None
