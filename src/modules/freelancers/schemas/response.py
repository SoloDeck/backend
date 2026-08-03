import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FreelancerCategoryResponse(BaseModel):
    slug: str
    name: str
    sub_skills: str


class FreelancerPublicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    professional_title: str | None
    bio: str | None
    avatar_url: str | None
    skills: list[str]
    service_categories: list[str]
    portfolio_url: str | None
    rating_average: float | None
    rating_count: int
    completed_project_count: int
    is_new: bool
    created_at: datetime

    # Token biểu mẫu tiếp nhận — để trang hồ sơ công khai dựng nút "Gửi yêu cầu" trỏ thẳng
    # tới `/bieu-mau/{token}` của chính freelancer này.
    #
    # Thiếu nó thì danh bạ là NGÕ CỤT: khách tìm ra người rồi không có đường liên hệ.
    #
    # KHÔNG phải rò rỉ: token sinh ra để freelancer tự đem đi chia sẻ, và cả hai truy vấn
    # đọc bảng này đều lọc `is_listed=True` — chỉ người TỰ CHỌN hiện công khai mới lộ.
    #
    # `None` ở hai trường hợp: (1) tài khoản cũ chưa có token, (2) trong danh sách tìm kiếm
    # — chỗ đó không cần nên không trả, cho payload gọn.  #Huynh
    intake_share_token: str | None = None
