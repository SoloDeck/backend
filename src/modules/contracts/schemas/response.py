import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class TermTemplateOption(BaseModel):
    """Một lựa chọn mẫu điều khoản cho freelancer.

    Bản trước chỉ trả `id` + `name`, nên bộ chọn KHÔNG THỂ hiện gì về nội dung — mọi mẫu mang
    chung một dòng phụ đề, hai mẫu khác nhau nhìn y hệt nhau. Nay kèm đủ để phân biệt: mẫu này
    điền những khối nào, thuộc nghề nào, và một trích đoạn ngắn.

    Cố ý KHÔNG trả nguyên `content`: bộ chọn chỉ cần đủ để chọn, không cần cả bài.  #Huynh
    """

    id: uuid.UUID
    name: str
    #: Slug nghề, `None` = mẫu dùng chung.
    profession: str | None = None
    #: Nhãn tiếng Việt của các khối THỰC SỰ có nội dung (chế độ AI).
    blocks: list[str] = []
    #: Trích ~120 ký tự của khối đầu tiên.
    preview: str = ""
    #: Các điều mẫu này đã soạn sẵn cho chế độ KHUNG. Rỗng = mẫu chưa soạn khung.
    skeleton_blocks: list[str] = []

class ContractResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deal_id: uuid.UUID
    proposal_id: uuid.UUID
    client_id: uuid.UUID
    owner_user_id: uuid.UUID
    version_number: int
    status: str
    content: dict
    client_snapshot: dict
    effective_date: date | None
    end_date: date | None
    signed_by_freelancer_at: datetime | None
    signed_by_client_at: datetime | None
    share_token: str | None
    created_at: datetime
    updated_at: datetime


class ContractExportResponse(BaseModel):
    status: str
    task_id: str | None = None
    download_url: str | None = None
