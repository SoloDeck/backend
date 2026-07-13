"""Chấm điểm deal: điểm sẵn sàng báo giá + khả năng chốt.

Vì sao có file này: trước đây "điểm AI" chỉ là một bảng tra ba nấc —

    _score_map = {"HOT": 80, "WARM": 50, "COLD": 20}

AI không hề chấm điểm, nó chỉ dán nhãn HOT/WARM/COLD rồi backend tra ra số. Giao
diện hiện "50 / 100 điểm tiềm năng" như thể có thang đo liên tục, trong khi thực tế
chỉ có ĐÚNG BA giá trị. Deal 20 triệu và deal 700 nghìn đều ra 50 điểm. Người dùng
nhìn là mất tin ngay, và đúng ra là phải mất tin.

Nguyên tắc ở đây:

1. AI chấm TỪNG tiêu chí, BACKEND cộng tổng. Không giao phép cộng cho LLM — chúng
   làm toán rất ẩu, bảo cộng là tự rước sai số vào một con số người dùng sẽ tin.
2. Nhãn HOT/WARM/COLD SUY RA TỪ điểm, không phải ngược lại. Một nguồn sự thật duy
   nhất, nhãn không bao giờ mâu thuẫn với điểm.
3. "Khả năng chốt" tính bằng CODE từ dữ kiện quan sát được (ngân sách so với giá thị
   trường, có deadline không, nguồn deal). KHÔNG hỏi AI, vì dữ liệu đầu vào không hề
   chứa thông tin về độ tin cậy của khách — hỏi là nó bịa.

#Huynh
"""

from typing import Any

# Điểm sẵn sàng báo giá: yêu cầu của khách đã đủ rõ để bạn báo giá chưa.
# CỐ Ý không đo "khách có đáng tin không" — dữ liệu đầu vào chỉ có mô tả yêu cầu,
# suy ra tính cách khách hàng từ đó là bịa.
READINESS_CRITERIA: dict[str, int] = {
    "scope": 30,  # Phạm vi công việc rõ tới đâu
    "budget": 25,  # Khách đã nêu ngân sách chưa
    "timeline": 20,  # Có mốc thời gian cụ thể không
    "detail": 15,  # Khách mô tả kỹ hay qua loa
    "context": 10,  # Bối cảnh, kênh, loại dịch vụ
}

READINESS_LABELS: dict[str, str] = {
    "scope": "Phạm vi công việc",
    "budget": "Ngân sách",
    "timeline": "Thời gian",
    "detail": "Mức độ chi tiết",
    "context": "Bối cảnh & kênh",
}

# Ngưỡng khớp đúng với frontend (hot >= 75, cold < 45) để nhãn và màu không lệch nhau.
HOT_THRESHOLD = 75
COLD_THRESHOLD = 45


def _clamp(value: Any, low: int, high: int) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return low
    return max(low, min(high, number))


def compute_readiness(raw_breakdown: Any) -> tuple[int, list[dict[str, Any]]]:
    """Cộng điểm từng tiêu chí thành tổng 0–100.

    Trả về ``(score, breakdown)`` với breakdown đã chuẩn hoá để giao diện hiện được
    "Ngân sách 25/25 · Thời gian 0/20". Chính bảng phân rã này mới làm người dùng tin:
    họ thấy bị trừ điểm ở đâu và vì sao, thay vì một con số rơi từ trên trời.  #Huynh
    """
    values: dict[str, Any] = raw_breakdown if isinstance(raw_breakdown, dict) else {}

    breakdown: list[dict[str, Any]] = []
    total = 0

    for key, max_points in READINESS_CRITERIA.items():
        entry = values.get(key)
        # Model có thể trả {"scope": 20} hoặc {"scope": {"points": 20, "reason": "..."}}
        if isinstance(entry, dict):
            points = _clamp(entry.get("points"), 0, max_points)
            reason = str(entry.get("reason") or "").strip()
        else:
            points = _clamp(entry, 0, max_points)
            reason = ""

        total += points
        breakdown.append(
            {
                "key": key,
                "label": READINESS_LABELS[key],
                "points": points,
                "max_points": max_points,
                "reason": reason,
            }
        )

    return _clamp(total, 0, 100), breakdown


def level_from_score(score: int) -> str:
    """HOT/WARM/COLD suy ra TỪ điểm — không để AI tự dán nhãn rồi tra ngược."""
    if score >= HOT_THRESHOLD:
        return "HOT"
    if score < COLD_THRESHOLD:
        return "COLD"
    return "WARM"


def compute_win_likelihood(
    *,
    budget_points: int,
    timeline_points: int,
    detail_points: int,
    estimated_value: Any,
    price_range_min: Any,
    source: str | None,
) -> dict[str, Any]:
    """Khả năng chốt deal — suy ra từ CHÍNH bảng chấm điểm, không hỏi AI, không dò chuỗi.

    Bản đầu tiên tôi viết sai và người dùng bắt được ngay: tôi xác định "khách có nêu
    thời hạn không" bằng cách dò chuỗi ::

        has_timeline = "không đủ thông tin" not in timeline_signal.lower()

    AI trả "Không có thông tin về thời gian thực hiện dự án" — KHÔNG chứa đúng cụm đó,
    nên điều kiện thành True và thời gian được chấm 25/25, trong khi bảng bên cạnh ghi
    0/20. Hai bảng nói ngược nhau ngay trên cùng một màn hình.

    Bài học: đừng bắt một sự thật quan trọng bằng cách dò chữ trong câu văn của LLM.
    Giờ mọi yếu tố đều lấy ĐIỂM SỐ từ bảng phân rã — cùng một nguồn sự thật, nên hai
    bảng không thể mâu thuẫn.

    Mỗi yếu tố kèm ``impact``: "positive" | "neutral" | "negative".  #Huynh
    """
    factors: list[dict[str, Any]] = []
    total = 0

    # 1. Ngân sách (0–30). Chỉ so sánh khi KHÁCH thực sự nêu ngân sách (budget_points > 0).
    #    "Giá trị dự kiến" trong form là freelancer tự ước — không phải bằng chứng gì cả.
    budget = _to_number(estimated_value)
    market_min = _to_number(price_range_min)

    if budget_points <= 0:
        factors.append(
            _factor(
                "budget",
                "Ngân sách",
                0,
                30,
                "neutral",
                "Khách chưa nêu ngân sách — chưa có gì để so với giá thị trường.",
            )
        )
    elif budget is None or market_min is None:
        total += 15
        factors.append(
            _factor(
                "budget",
                "Ngân sách",
                15,
                30,
                "neutral",
                "Khách có nói về ngân sách nhưng chưa quy ra được con số để so sánh.",
            )
        )
    elif budget >= market_min:
        total += 30
        factors.append(
            _factor(
                "budget",
                "Ngân sách",
                30,
                30,
                "positive",
                "Ngân sách nằm trong khoảng giá thị trường.",
            )
        )
    elif budget >= market_min * 0.7:
        total += 15
        factors.append(
            _factor(
                "budget",
                "Ngân sách",
                15,
                30,
                "neutral",
                "Ngân sách hơi thấp so với giá thị trường — có thể thương lượng.",
            )
        )
    else:
        factors.append(
            _factor(
                "budget",
                "Ngân sách",
                0,
                30,
                "negative",
                "Ngân sách thấp hơn nhiều so với giá thị trường — nguy cơ không chốt được.",
            )
        )

    # 2. Thời gian (0–25) — quy đổi thẳng từ điểm timeline của bảng phân rã.
    timeline_max = READINESS_CRITERIA["timeline"]
    timeline_scaled = _scale(timeline_points, timeline_max, 25)
    total += timeline_scaled
    factors.append(
        _factor(
            "timeline",
            "Thời gian",
            timeline_scaled,
            25,
            _impact(timeline_scaled, 25),
            "Khách đã nêu mốc thời gian cụ thể."
            if timeline_scaled >= 19
            else "Khách chỉ nói mơ hồ về thời gian."
            if timeline_scaled > 0
            else "Khách chưa nêu thời hạn — chưa rõ mức độ cần gấp.",
        )
    )

    # 3. Nguồn deal (0–25): khách được giới thiệu dễ chốt hơn khách lạ.
    source_points, source_impact, source_reason = _source_signal(source)
    total += source_points
    factors.append(
        _factor("source", "Nguồn deal", source_points, 25, source_impact, source_reason)
    )

    # 4. Độ chi tiết khách tự mô tả (0–20): người bỏ công mô tả kỹ là người nghiêm túc.
    detail_scaled = _scale(detail_points, READINESS_CRITERIA["detail"], 20)
    total += detail_scaled
    factors.append(
        _factor(
            "detail",
            "Mức độ chi tiết",
            detail_scaled,
            20,
            _impact(detail_scaled, 20),
            "Khách mô tả yêu cầu khá kỹ."
            if detail_scaled >= 13
            else "Khách mô tả sơ sài — khó nắm được nhu cầu thật."
            if detail_scaled > 0
            else "Khách gần như không mô tả gì.",
        )
    )

    score = _clamp(total, 0, 100)
    return {
        "score": score,
        "level": "high" if score >= 70 else "low" if score < 40 else "medium",
        "factors": factors,
    }


def _scale(points: Any, from_max: int, to_max: int) -> int:
    """Quy đổi điểm từ thang này sang thang khác."""
    value = _clamp(points, 0, from_max)
    if from_max <= 0:
        return 0
    return _clamp(round(value / from_max * to_max), 0, to_max)


def _impact(points: int, max_points: int) -> str:
    ratio = points / max_points if max_points else 0
    if ratio >= 0.7:
        return "positive"
    if ratio >= 0.4:
        return "neutral"
    return "negative"


def _factor(
    key: str, label: str, points: int, max_points: int, impact: str, reason: str
) -> dict[str, Any]:
    """``key`` để frontend GHÉP yếu tố này với đúng tiêu chí bên thang sẵn sàng.

    Ba trong bốn yếu tố ở đây (budget, timeline, detail) nói về CÙNG dữ kiện với thang
    sẵn sàng, chỉ khác trọng số. Hiện thành hai bảng tách rời là kể một chuyện hai lần —
    người dùng thấy "Thời gian 0/20" rồi ngay cạnh "Thời gian 0/25" thì đọc rất khó chịu.
    Có key thì frontend gộp được về một dòng.  #Huynh
    """
    return {
        "key": key,
        "label": label,
        "points": points,
        "max_points": max_points,
        "impact": impact,
        "reason": reason,
    }


def _source_signal(source: str | None) -> tuple[int, str, str]:
    if source == "referral":
        return 25, "positive", "Khách được giới thiệu — tỉ lệ chốt thường cao hơn."
    if source == "inbound":
        return 15, "neutral", "Khách tự tìm đến — đã có nhu cầu sẵn."
    if source == "outreach":
        return 5, "negative", "Bạn chủ động tiếp cận — khách chưa chắc đã có nhu cầu."
    return 10, "neutral", "Chưa rõ nguồn deal."


def _to_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
