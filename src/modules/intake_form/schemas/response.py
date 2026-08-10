import uuid

from pydantic import BaseModel, ConfigDict


class IntakeFormFieldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    field_key: str
    label: str
    placeholder: str | None
    field_type: str
    is_required: bool
    is_visible: bool
    sort_order: int


class IntakeFormResponse(BaseModel):
    id: uuid.UUID | None
    title: str
    description: str | None
    is_active: bool
    share_url: str | None
    fields: list[IntakeFormFieldResponse]


class PublicIntakeFormFieldResponse(BaseModel):
    field_key: str
    label: str
    placeholder: str | None
    field_type: str
    is_required: bool


class PublicIntakeFormConfigResponse(BaseModel):
    title: str
    description: str | None
    freelancer_name: str
    fields: list[PublicIntakeFormFieldResponse]
    # Freelancer còn nhận yêu cầu mới không. Trang công khai vẫn hiện hồ sơ khi tắt — link đã
    # phát cho khách không được biến thành trang lỗi — nhưng thay chỗ biểu mẫu bằng một câu
    # nói rõ, thay vì để khách điền xong mới ăn lỗi.
    is_active: bool = True


class PublicProfileResponse(BaseModel):
    """Hồ sơ freelancer hiện trên trang chia sẻ, đứng trước biểu mẫu tiếp nhận.

    CỐ Ý không có `id`: định danh duy nhất của trang này là `share_token`. Trả thêm id là
    mở lại đúng thứ vừa bỏ — có id thì dò được, dò được thì liệt kê được, liệt kê được thì
    thành danh bạ. Cũng không trả `email`/`phone` (trang này ai có link đều xem được), và
    không trả `rating_*`/`completed_project_count` vì SoloDesk không xếp hạng freelancer.

    Không đặt `from_attributes`: `skills` nullable trong DB, dựng tay ở service để chỗ nào
    rỗng cũng ra `[]` chứ không ra `None`.  #Huynh
    """

    full_name: str
    professional_title: str | None
    bio: str | None
    avatar_url: str | None
    cover_url: str | None
    brand_color: str | None
    skills: list[str]
    portfolio_url: str | None
