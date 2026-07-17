import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, computed_field

from src.ai.lead_qualifier.scoring import COLD_THRESHOLD, level_from_score


class DealResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    client_id: uuid.UUID
    title: str
    stage: str
    source: str | None
    estimated_value: Decimal | None
    actual_value: Decimal | None
    currency: str
    notes: str | None
    desired_timeline: str | None
    project_type: str | None
    service_category: str | None
    pricing_tier: str | None
    ai_qualification_score: int | None
    ai_qualification_recommendation: str | None
    ai_qualification_reasoning: str | None
    ai_qualification_project_type: str | None
    ai_qualification_budget_signal: str | None
    ai_qualification_timeline_signal: str | None
    ai_qualification_urgency_signal: str | None
    ai_qualification_red_flags: list[str] | None
    ai_qualification_detected_signals: list[dict] | None
    ai_qualification_suggested_actions: list[str] | None
    ai_qualification_next_step: str | None
    ai_qualification_price_range_min: int | None
    ai_qualification_price_range_max: int | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ai_level(self) -> str | None:
        """HOT/WARM/COLD — DÙNG CHUNG ngưỡng với bộ chấm điểm.

        Trước đây chỗ này tự hardcode ngưỡng riêng (>=80 hot, >=50 warm), lệch hẳn với
        `scoring.py` (HOT=75, COLD=45). Deal 78 điểm: bảng chấm điểm kết luận HOT, còn API
        trả về "warm" — hai nguồn sự thật đá nhau, và người dùng nhìn thấy cả hai.  #Huynh
        """
        if self.ai_qualification_score is None:
            return None
        return level_from_score(self.ai_qualification_score).lower()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_ai_qualified(self) -> bool:
        """Đủ điều kiện báo giá = không phải COLD (cùng ngưỡng với bảng chấm điểm)."""
        if self.ai_qualification_score is None:
            return False
        return self.ai_qualification_score >= COLD_THRESHOLD


class IntakeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    client_id: uuid.UUID
    # Phiếu này thuộc deal nào. Frontend TRƯỚC ĐÂY ghép phiếu vào deal theo `client_id` —
    # cùng cái bug với backend: một khách gửi form hai lần thì deal cũ hiện mô tả của dự
    # án mới. Nullable vì phiếu cũ không biết thuộc deal nào.  #Huynh
    deal_id: uuid.UUID | None = None
    inquiry_text: str
    estimated_budget: str | None
    desired_timeline: str | None
    source: str | None
    submitted_at: datetime
    created_at: datetime


class PublicIntakeResponse(BaseModel):
    """Minimal confirmation returned to an unauthenticated intake submitter.

    Deliberately excludes owner identity and pipeline internals.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    submitted_at: datetime
    message: str = "Thank you — your inquiry has been received."


class LeadScoreHistoryResponse(BaseModel):
    """Một lần chấm điểm đã lưu — kèm PHẦN CHỨNG MINH, không chỉ con số.

    Trước đây bảng "Căn cứ chấm điểm" chỉ nằm ở localStorage của trình duyệt: đổi máy hay
    xoá cache là deal vẫn hiện điểm nhưng mất sạch căn cứ. Giờ đọc từ server.  #Huynh
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    score: int
    reasoning: str
    generated_at: datetime
    model_version: str

    project_type: str | None = None
    budget_signal: str | None = None
    timeline_signal: str | None = None
    urgency_signal: str | None = None
    red_flags: list | None = None

    # Bản ghi CŨ (trước khi thêm mấy cột này) không có -> None. Giao diện phải chịu được.
    breakdown: list | None = None
    next_step: str | None = None
    detected_signals: list | None = None
    prompt_version: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def level(self) -> str:
        """HOT/WARM/COLD suy từ điểm — dùng CHUNG ngưỡng với bộ chấm điểm."""
        return level_from_score(self.score).lower()
