import uuid
from dataclasses import dataclass
from datetime import datetime

from src.ai.lead_qualifier.scoring import COLD_THRESHOLD, level_from_score
from src.modules.deals.domain.value_objects.ai_confidence import AIConfidence


@dataclass
class LeadScore:
    """AI-generated qualification score for a deal.

    Every LeadScore belongs to exactly one Deal. Score is 0–100.
    Confidence is 0.0–1.0.
    """

    id: uuid.UUID
    deal_id: uuid.UUID
    score: int  # 0–100
    confidence: AIConfidence
    reasoning: str
    model_version: str
    generated_at: datetime

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError(f"Score must be 0–100, got {self.score}")
        if not self.reasoning.strip():
            raise ValueError("Reasoning must not be empty")

    @property
    def is_qualified(self) -> bool:
        """Đủ điều kiện theo đuổi = không phải COLD.

        Trước đây chỗ này hardcode `>= 60`, trong khi `DealResponse.is_ai_qualified` dùng
        ngưỡng 45. Cùng một deal 50 điểm: API trả `is_ai_qualified = true` nhưng
        `recommendation = "pass"` — hai câu trả lời ngược nhau cho cùng một con số, và người
        dùng nhìn thấy cả hai. Giờ cả hai đọc chung `COLD_THRESHOLD`.  #Huynh
        """
        return self.score >= COLD_THRESHOLD

    @property
    def level(self) -> str:
        """Ngưỡng cũ ở đây là 80/50, lệch hẳn với 75/45 của bộ chấm điểm.

        Deal 78 điểm: bảng chấm điểm kết luận HOT, tầng domain nói WARM. Một thang điểm
        không được có hai định nghĩa nhãn.  #Huynh
        """
        return level_from_score(self.score).lower()
