import uuid
from datetime import datetime

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
    #: Các mục mẫu này đã soạn sẵn cho chế độ KHUNG. Rỗng = mẫu chưa soạn khung, chọn nó ở tab
    #: "Tự soạn từ khung" thì phần thân freelancer phải tự điền — phải nói trước, không để họ
    #: chọn xong mới phát hiện tờ giấy gần như trống.
    skeleton_blocks: list[str] = []

class ProposalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deal_id: uuid.UUID
    owner_user_id: uuid.UUID
    version_number: int
    status: str
    content: dict
    ai_generated: bool
    share_token: str | None
    share_expires_at: datetime | None
    sent_at: datetime | None
    responded_at: datetime | None
    created_at: datetime
    updated_at: datetime
