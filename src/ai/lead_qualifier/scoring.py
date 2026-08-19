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

from dataclasses import dataclass
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

# Ba tiêu chí trả lời câu "CÓ báo giá được không", ba tiêu chí còn lại chỉ trả lời "báo giá
# TỐT tới đâu". Tổng ba cái này đúng bằng HOT_THRESHOLD — không phải trùng hợp mà là định
# nghĩa của HOT: đủ ba thứ cốt lõi thì báo giá tự tin.
ESSENTIAL_CRITERIA: tuple[str, ...] = ("scope", "budget", "timeline")


@dataclass(frozen=True)
class RubricLevel:
    """Một nấc điểm của một tiêu chí.

    ``state`` = deal đang đứng ở nấc này thì nghĩa là gì.
    ``requirement`` = phải có gì thì mới ĐẠT nấc này.

    Hai câu này khác vai: ``state`` giải thích hiện tại, ``requirement`` chỉ đường đi lên.
    """

    points: int
    state: str
    requirement: str


# BẢNG BAREM — vì sao MẤT điểm, tra được bằng code chứ không phải hỏi AI.
#
# Trước đây màn hình chỉ trả lời được nửa câu hỏi: "vì sao ĐƯỢC 27 điểm" (AI trích dữ kiện
# khách nói). Nửa còn lại — "vì sao KHÔNG được 73 điểm kia, và làm sao lên 100" — không ai
# trả lời được. Mẹo duy nhất là bảo AI viết thêm câu bắt đầu bằng "Để lên tối đa: " rồi
# frontend cắt chuỗi theo đúng cụm đó; AI viết lệch một chữ là mất sạch phần giải thích.
#
# Nhưng thang điểm vốn RỜI RẠC và mỗi nấc có điều kiện viết sẵn (xem prompts/system.txt),
# nên phần thiếu TRA BẢNG RA ĐƯỢC. Đó cũng là câu trả lời mạnh khi bảo vệ: phần được điểm
# do AI đọc yêu cầu khách, phần mất điểm là tra barem — không phải AI phán.
#
# Ba nơi phải khớp nhau: bảng này, mục 4 của docs/domains/lead-qualifier-scoring.md, và
# phần "ĐIỂM LÀ CÁC MỨC RỜI RẠC" trong prompts/system.txt. Có test giữ.
#
# Khai theo thứ tự GIẢM DẦN — phần tử đầu là trần của tiêu chí.  #Huynh
RUBRIC_LEVELS: dict[str, tuple[RubricLevel, ...]] = {
    "scope": (
        RubricLevel(
            30,
            "Khách đã nêu rõ các hạng mục và sản phẩm bàn giao.",
            "Khách liệt kê đủ hạng mục cần làm và nói rõ sẽ bàn giao những gì.",
        ),
        RubricLevel(
            20,
            "Biết loại việc và vài hạng mục, nhưng chưa đủ để báo giá chắc.",
            "Khách cho biết loại việc kèm ít nhất vài hạng mục cụ thể.",
        ),
        RubricLevel(
            12,
            "Chỉ có tên dự án, chưa có hạng mục nào.",
            "Khách cho biết tên hoặc loại dự án.",
        ),
        RubricLevel(
            0,
            "Chưa rõ khách cần làm gì.",
            "Không có thông tin nào về công việc phải làm.",
        ),
    ),
    "budget": (
        RubricLevel(
            25,
            "Khách đã nêu con số ngân sách cụ thể.",
            'Khách nêu CON SỐ ngân sách ("120 triệu", "50–80 triệu").',
        ),
        RubricLevel(
            15,
            "Khách có nói về tiền nhưng chưa ra con số.",
            'Khách nói ước lượng về tiền ("tầm vài chục triệu", "ngân sách hạn chế").',
        ),
        RubricLevel(
            0,
            "Khách chưa nhắc gì tới tiền.",
            "Không có thông tin nào về ngân sách.",
        ),
    ),
    "timeline": (
        RubricLevel(
            20,
            "Khách đã nêu mốc thời gian cụ thể.",
            'Khách nêu MỐC cụ thể ("trước 30/09/2026", "trong 6 tuần").',
        ),
        RubricLevel(
            10,
            "Khách chỉ nói mơ hồ về thời gian.",
            'Khách nói về thời gian dù mơ hồ ("càng sớm càng tốt", "gấp").',
        ),
        RubricLevel(
            0,
            "Khách chưa nhắc tới thời hạn.",
            "Không có thông tin nào về thời gian.",
        ),
    ),
    "detail": (
        RubricLevel(
            15,
            "Khách mô tả kỹ, có ràng buộc cụ thể.",
            "Khách mô tả kỹ kèm ràng buộc cụ thể: số lượng, hiện trạng, yêu cầu kỹ thuật.",
        ),
        RubricLevel(
            8,
            "Khách có mô tả nhưng sơ sài, một hai câu.",
            "Khách có mô tả yêu cầu, dù chỉ một hai câu.",
        ),
        RubricLevel(
            0,
            "Khách không mô tả gì, hoặc mô tả không đọc được.",
            "Không có mô tả nào dùng được.",
        ),
    ),
    "context": (
        RubricLevel(
            10,
            "Biết rõ ngành nghề, quy mô và hiện trạng của khách.",
            "Khách cho biết ngành nghề, quy mô và hiện trạng.",
        ),
        RubricLevel(
            5,
            "Chỉ biết một phần bối cảnh khách hàng.",
            "Khách cho biết một phần bối cảnh: ngành nghề, hoặc quy mô, hoặc hiện trạng.",
        ),
        RubricLevel(
            0,
            "Không có thông tin bối cảnh nào.",
            "Không có thông tin nào về khách hàng.",
        ),
    ),
}

# Câu hỏi mẫu gửi khách khi tiêu chí chưa đạt trần.
#
# AI được yêu cầu viết câu hỏi bám đúng dự án (khoá "question" trong score_breakdown), nhưng
# prompt là lời khuyên chứ không phải ràng buộc. Thiếu thì rơi về đây — màn hình KHÔNG BAO
# GIỜ được để trống ô "nên hỏi gì", vì đó chính là việc tiếp theo người dùng cần làm.
DEFAULT_ASK: dict[str, str] = {
    "scope": "Anh/chị cần làm cụ thể những hạng mục nào, và bàn giao cho mình những gì ạ?",
    "budget": "Anh/chị dự trù ngân sách khoảng bao nhiêu cho dự án này ạ?",
    "timeline": "Anh/chị cần bàn giao trước thời điểm nào ạ?",
    "detail": "Anh/chị mô tả kỹ hơn giúp mình yêu cầu cụ thể được không ạ — số lượng, "
    "hiện trạng, ràng buộc kỹ thuật?",
    "context": "Bên anh/chị hoạt động trong ngành nào và quy mô ra sao ạ?",
}

# Hỏi được khách rồi thì GHI VÀO ĐÂU. Không có bảng này thì người dùng biết mình thiếu gì
# mà vẫn không biết điền vào đâu — đúng chỗ luồng nghiệp vụ đang đứt.
#
# `client_budget` là ô ghi lại LỜI KHÁCH, khác hẳn `estimated_value` là phỏng đoán của
# freelancer và bị cấm chấm điểm (xem _build_inquiry_context).
FILL_FIELD: dict[str, str] = {
    "scope": "notes",
    "budget": "client_budget",
    "timeline": "desired_timeline",
    "detail": "notes",
    "context": "notes",
}


def _clamp(value: Any, low: int, high: int) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return low
    return max(low, min(high, number))


def _level_at(key: str, points: int) -> RubricLevel:
    """Nấc mà số điểm này đang đứng — nấc cao nhất mà điểm còn với tới."""
    levels = RUBRIC_LEVELS[key]
    for level in levels:
        if points >= level.points:
            return level
    return levels[-1]


def snap_to_level(key: str, points: int) -> int:
    """Kéo điểm về đúng một nấc hợp lệ của barem, làm tròn XUỐNG.

    Prompt đã cấm chấm số nằm giữa ("chấm 22 khi bảng chỉ có 20 và 25 là sai luật"), nhưng
    prompt là lời khuyên. Không chặn ở đây thì cả lập luận "thang điểm tái lập được" chỉ
    đứng trên thiện chí của model — mà hội đồng hỏi "lấy gì đảm bảo" thì không trả lời được.

    Làm tròn XUỐNG chứ không phải về nấc gần nhất: cùng một luật với phần chống phồng điểm
    trong prompt — thà chấm thấp rồi đi hỏi khách, còn hơn chấm hào phóng rồi báo giá mù.

    Kéo về nấc cũng khiến phần giải thích khỏi tự mâu thuẫn: điểm 22 mà bảng ghi "đang ở nấc
    20" thì người dùng đọc xong không hiểu con số 22 ở đâu ra.  #Huynh
    """
    if key not in RUBRIC_LEVELS:
        return points
    return _level_at(key, points).points


def explain_gap(key: str, points: int) -> dict[str, Any] | None:
    """Vì sao tiêu chí này mất điểm, và cần gì để lên từng nấc. ``None`` khi đã đạt trần.

    Toàn bộ nội dung tra từ ``RUBRIC_LEVELS`` — không có chữ nào của AI ở đây.

    ``steps`` liệt kê các nấc CÒN LẠI phía trên, từ thấp lên cao, kèm ``gain`` là số điểm
    thu được nếu lên tới đó. Có nhiều nấc thì hiện nhiều: khách chỉ nói mơ hồ về tiền vẫn
    hơn không nói gì, và người dùng cần thấy cả bậc thang chứ không chỉ đỉnh thang.
    """
    levels = RUBRIC_LEVELS.get(key)
    if levels is None:
        return None

    max_points = levels[0].points
    if points >= max_points:
        return None

    return {
        "lost_points": max_points - points,
        "current_state": _level_at(key, points).state,
        "steps": [
            {
                "points": level.points,
                "gain": level.points - points,
                "requirement": level.requirement,
            }
            for level in reversed(levels)
            if level.points > points
        ],
        "fill_field": FILL_FIELD.get(key),
    }


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
            evidence = str(entry.get("evidence") or "").strip()
            question = str(entry.get("question") or "").strip()
        else:
            points = _clamp(entry, 0, max_points)
            reason = ""
            evidence = ""
            question = ""

        points = snap_to_level(key, points)
        gap = explain_gap(key, points)

        total += points
        breakdown.append(
            {
                "key": key,
                "label": READINESS_LABELS[key],
                "points": points,
                "max_points": max_points,
                "reason": reason,
                # DỮ KIỆN THẬT lấy từ lời khách — "trước 30/09/2026", "120 triệu", chứ không
                # phải nhận xét của AI. `reason` trả lời "vì sao được ngần này điểm";
                # `evidence` trả lời "khách đã nói ĐÚNG CÁI GÌ".
                #
                # Đây là thứ freelancer thật sự cần: nắm được các mốc quan trọng mà KHÔNG
                # phải mở file PDF ra đọc. Rỗng = khách không hề nhắc tới, và giao diện phải
                # nói thẳng điều đó thay vì để trống.
                #
                # 0 điểm thì ÉP evidence về None ngay tại đây, không tin model tự giữ luật:
                # 0 điểm nghĩa là khách không nói gì — mà không nói gì thì lấy đâu ra dữ kiện
                # để trích. Model đôi lúc vẫn điền một câu suy đoán vào, và một câu bịa nằm
                # ngay dưới dòng "Ngân sách 0/25" thì còn tệ hơn là để trống.  #Huynh
                "evidence": (evidence or None) if points > 0 else None,
                # PHẦN MẤT ĐIỂM — tra từ barem, không phải chữ của AI. `None` = đã đạt trần.
                "gap": gap,
                # Câu hỏi gửi khách. AI viết cho bám dự án, hỏng thì rơi về câu mẫu; đạt
                # trần rồi thì không hỏi gì nữa.
                "ask": (question or DEFAULT_ASK.get(key)) if gap else None,
            }
        )

    return _clamp(total, 0, 100), breakdown


def build_gap_summary(score: int, breakdown: list[dict[str, Any]]) -> dict[str, Any]:
    """Gộp phần thiếu của cả 5 tiêu chí thành một bản tóm tắt cho giao diện.

    Sắp GIẢM DẦN theo số điểm mất: việc đáng làm nhất nằm trên cùng. Hỏi khách một câu về
    ngân sách được 25 điểm, trong khi làm rõ bối cảnh chỉ được 10 — thứ tự đó phải nhìn thấy
    ngay, đừng bắt người dùng tự so.

    ``essential_missing`` là các tiêu chí thiết yếu chưa đạt trần. Còn tên nào trong đây thì
    chắc chắn chưa thể HOT, vì HOT = 75 = đúng tổng ba tiêu chí ấy.

    Bản ghi `lead_scores` CŨ chỉ lưu ``breakdown`` gồm điểm và lý do, chưa có khoá ``gap``.
    Không tính lại thì mở lại một bản đánh giá cũ sẽ thấy màn hình trống đúng chỗ quan trọng
    nhất. Mà gap suy ra thuần tuý từ ``(key, points)``, nên tính lại được — đó cũng là lý do
    KHÔNG lưu gap xuống database: lưu thêm một bản sao chỉ để nó có ngày lệch với barem.
    """
    order = list(READINESS_CRITERIA)
    gaps: list[dict[str, Any]] = []

    for item in breakdown:
        key = str(item.get("key") or "")
        if key not in RUBRIC_LEVELS:
            continue

        points = _clamp(item.get("points"), 0, READINESS_CRITERIA[key])
        gap = item.get("gap") or explain_gap(key, points)
        if not gap:
            continue

        gaps.append(
            {
                "key": key,
                "label": item.get("label") or READINESS_LABELS[key],
                "points": points,
                "max_points": READINESS_CRITERIA[key],
                "ask": item.get("ask") or DEFAULT_ASK.get(key),
                **gap,
            }
        )

    gaps.sort(key=lambda gap: (-int(gap["lost_points"]), order.index(str(gap["key"]))))

    return {
        "lost_points": max(0, sum(READINESS_CRITERIA.values()) - score),
        "points_to_hot": max(0, HOT_THRESHOLD - score),
        "essential_missing": [gap["key"] for gap in gaps if gap["key"] in ESSENTIAL_CRITERIA],
        "gaps": gaps,
    }


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
            (
                "Khách đã nêu mốc thời gian cụ thể."
                if timeline_scaled >= 19
                else (
                    "Khách chỉ nói mơ hồ về thời gian."
                    if timeline_scaled > 0
                    else "Khách chưa nêu thời hạn — chưa rõ mức độ cần gấp."
                )
            ),
        )
    )

    # 3. Nguồn deal (0–25): khách được giới thiệu dễ chốt hơn khách lạ.
    source_points, source_impact, source_reason, source_evidence = _source_signal(source)
    total += source_points
    factors.append(
        _factor(
            "source",
            "Nguồn deal",
            source_points,
            25,
            source_impact,
            source_reason,
            evidence=source_evidence,
        )
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
            (
                "Khách mô tả yêu cầu khá kỹ."
                if detail_scaled >= 13
                else (
                    "Khách mô tả sơ sài — khó nắm được nhu cầu thật."
                    if detail_scaled > 0
                    else "Khách gần như không mô tả gì."
                )
            ),
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
    key: str,
    label: str,
    points: int,
    max_points: int,
    impact: str,
    reason: str,
    evidence: str | None = None,
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
        # Chỉ `source` có evidence riêng ở thang này — nó là yếu tố DUY NHẤT không lấy dữ
        # kiện từ lời khách mà từ chính hệ thống (deal vào qua kênh nào). Các yếu tố còn lại
        # (budget/timeline/detail) dùng chung evidence với thang sẵn sàng, nên không lặp
        # lại ở đây.  #Huynh
        "evidence": evidence,
        "impact": impact,
        "reason": reason,
    }


# Nhãn tiếng Việt cho từng kênh — dùng làm `evidence` của yếu tố "Nguồn deal".
SOURCE_LABELS: dict[str, str] = {
    "referral": "Được người khác giới thiệu",
    "inbound": "Khách tự tìm đến (biểu mẫu tiếp nhận, website)",
    "outreach": "Bạn chủ động tiếp cận khách",
    "platform": "Qua nền tảng freelance",
    "other": "Kênh khác",
}


def _source_signal(source: str | None) -> tuple[int, str, str, str | None]:
    evidence = SOURCE_LABELS.get(source or "")
    if source == "referral":
        return 25, "positive", "Khách được giới thiệu — tỉ lệ chốt thường cao hơn.", evidence
    if source == "inbound":
        return 15, "neutral", "Khách tự tìm đến — đã có nhu cầu sẵn.", evidence
    if source == "outreach":
        return 5, "negative", "Bạn chủ động tiếp cận — khách chưa chắc đã có nhu cầu.", evidence
    return 10, "neutral", "Chưa rõ nguồn deal.", evidence


def _to_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


# Dự án freelance thật không bao giờ dưới 500.000 VNĐ. Con số nhỏ hơn thế gần như chắc
# chắn là model viết tắt theo "triệu".
_MIN_REALISTIC_PRICE = 500_000
_SHORTHAND_THRESHOLD = 1_000


def normalize_price_range(low: Any, high: Any) -> tuple[int, int]:
    """Chữa lại khoảng giá khi model viết tắt đơn vị.

    llama-4-scout trả về ``price_range_min: 30, price_range_max: 50`` — nó đang nghĩ
    "30–50 triệu" nhưng viết mỗi con số. Giao diện in ra thành "30 ₫ - 50 ₫", nhìn là
    buồn cười, và freelancer không tin nổi cái gì nữa.

    Prompt đã siết (bắt viết đủ chữ số, nêu ví dụ, nói rõ dự án thật không dưới 500.000).
    Nhưng prompt là lời khuyên, không phải ràng buộc — nên chặn thêm ở đây.

    Quy tắc: giá trị nằm trong (0, 1000) thì CHẮC CHẮN là viết tắt theo triệu — nhân lên.
    Giá trị 1.000–500.000 thì đáng ngờ nhưng không đoán được ý model, nên trả 0: **thà
    không hiện gì còn hơn hiện một con số sai** rồi freelancer báo giá theo.  #Huynh
    """

    def _one(value: Any) -> int:
        try:
            number = float(value or 0)
        except (TypeError, ValueError):
            return 0
        if number <= 0:
            return 0
        if number < _SHORTHAND_THRESHOLD:
            return int(number * 1_000_000)
        if number < _MIN_REALISTIC_PRICE:
            return 0
        return int(number)

    return _one(low), _one(high)
