"""Bộ định giá — LUẬT BẰNG CODE, không giao cho LLM.

Nguyên tắc trung tâm của cả module: **AI KHÔNG BAO GIỜ XUẤT RA MỘT CON SỐ TIỀN.**

AI chỉ trả về hai thứ nó thật sự giỏi:
  1. Ba hệ số điều chỉnh RỜI RẠC (phức tạp / quy mô), kèm lý do trích được từ dữ liệu.
  2. Tỉ trọng công sức tương đối giữa các hạng mục (%).

Mọi phép tiền — mốc neo, nhân hệ số, làm tròn, tính khoảng — nằm ở file này, bằng Python
thuần, kiểm chứng được bằng unit test.

VÌ SAO PHẢI THẾ:

Bản báo giá cũ ra "0 ₫" kèm dòng "Giá sẽ được báo sau khi thống nhất phạm vi công việc".
Lý do: prompt cấm AI tự nghĩ ra số, và bắt nó chép đúng ô "Giá trị dự kiến" của freelancer.
Không nhập ô đó thì không có giá. Nghĩa là **AI không hề định giá — freelancer định giá,
AI chép lại**. Vô dụng ở đúng cái việc khó nhất.

Nhưng lối thoát KHÔNG phải "cho AI bịa số". Mức giá theo giờ thì freelancer tự khai (gõ
5 triệu/giờ là cả bản báo giá thành trò cười), còn để LLM phán "dự án này 59 triệu" thì
không ai kiểm chứng nổi con số đó ở đâu ra.

Lối thoát là NEO VÀO DỮ LIỆU CÓ THẬT rồi để AI làm phần ĐIỀU CHỈNH TƯƠNG ĐỐI:

    Mốc neo (giá THẬT freelancer đã chốt cho việc cùng loại)
      × Độ phức tạp   [AI chấm, rời rạc]
      × Quy mô        [AI chấm, rời rạc]
      × Độ gấp        [CODE tính từ deadline — không hỏi AI]
      = Giá đề xuất  ->  nới thành KHOẢNG theo độ tin cậy của mốc neo
      ->  FREELANCER CHỐT con số cuối cùng

Và vòng lặp khép kín: deal chốt xong ghi `actual_value` -> chính nó là mốc neo lần sau.
Hệ thống càng dùng càng đúng, vì nó học từ giá freelancer THẬT SỰ chốt được.  #Huynh
"""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from typing import Any, Literal

Confidence = Literal["high", "medium", "low"]

# --- Hệ số điều chỉnh -------------------------------------------------------------
#
# RỜI RẠC, không phải dải. Cho AI một dải ("1.0–1.5") là mời nó chọn bừa, và chấm cùng một
# deal hai lần ra hai giá khác nhau. Bài học rút ra từ thang chấm điểm: đã phải đổi từ dải
# sang mức rời rạc mới hết cảnh chấm 70 rồi 80 trên cùng một dữ liệu.  #Huynh

COMPLEXITY_FACTORS: dict[str, Decimal] = {
    "simple": Decimal("0.8"),  # ít hạng mục, không tích hợp gì lạ
    "normal": Decimal("1.0"),  # như phần lớn dự án cùng loại
    "complex": Decimal("1.3"),  # nhiều phân hệ, tích hợp bên thứ ba
    "very_complex": Decimal("1.6"),  # yêu cầu kỹ thuật đặc biệt, rủi ro cao
}

SCALE_FACTORS: dict[str, Decimal] = {
    "small": Decimal("0.8"),
    "normal": Decimal("1.0"),
    "large": Decimal("1.3"),
    "very_large": Decimal("1.6"),
}

# Độ gấp: CODE tự tính từ số ngày còn lại tới hạn khách nêu. KHÔNG hỏi AI.
#
# Đây là dòng để chỉ vào khi hội đồng hỏi "chỗ nào trong định giá không phải AI đoán".
# Gấp thì tính thêm tiền — vì phải gạt việc khác sang một bên, làm ngoài giờ, và mất cơ hội
# nhận deal khác.
RUSH_URGENT_DAYS = 14
RUSH_TIGHT_DAYS = 30
RUSH_FACTOR_URGENT = Decimal("1.35")
RUSH_FACTOR_TIGHT = Decimal("1.15")
RUSH_FACTOR_NORMAL = Decimal("1.0")

# --- Độ rộng khoảng chào ----------------------------------------------------------
#
# Khoảng rộng hay hẹp là LỜI THÚ NHẬN về mức độ hệ thống dám chắc.
#
# Có 3 deal thật để neo -> biết khá rõ -> khoảng hẹp (±10%).
# Chưa có gì, phải nhờ AI ước giá thị trường -> khoảng rộng toác (±30%), và màn hình ghi
# thẳng "độ tin cậy: thấp". Không giấu dốt bằng một con số trông có vẻ chắc chắn.
RANGE_SPREAD: dict[Confidence, Decimal] = {
    "high": Decimal("0.10"),
    "medium": Decimal("0.20"),
    "low": Decimal("0.30"),
}

# Cần ít nhất ngần này deal đã chốt thì mốc neo mới đáng tin.
MIN_DEALS_FOR_HIGH_CONFIDENCE = 3

# Làm tròn tới 500.000 ₫. Báo giá "59.283.417 ₫" trông như máy in ra, không ai chào giá
# kiểu đó. "59.500.000 ₫" mới giống một con người đã cân nhắc.
ROUND_TO = Decimal("500000")


@dataclass
class PriceAnchor:
    """Mốc neo giá + xuất xứ của nó.

    `source` và `confidence` PHẢI đi tới tận giao diện. Người dùng có quyền biết con số này
    dựa trên 5 deal thật của họ hay chỉ là AI đoán mò.
    """

    value: Decimal
    confidence: Confidence
    source: str
    sample_size: int = 0

    # Mốc neo này đã là giá RIÊNG của dự án này, hay chỉ là mặt bằng chung?
    #
    # Phân biệt này quyết định có nhân hệ số hay không, và nếu sai thì SAI TIỀN THẬT:
    #
    # - Lịch sử deal đã chốt = MẶT BẰNG CHUNG của freelancer ("dự án điển hình của tôi
    #   khoảng 38 triệu"). Dự án đang xét phức tạp hơn thì PHẢI nhân hệ số lên.
    #
    # - Giá thị trường AI ước = giá RIÊNG cho ĐÚNG dự án này. AI đã đọc mô tả, đã thấy 5
    #   phân hệ và 4 chi nhánh rồi mới ra con số. Nhân thêm ×1.3 (phức tạp) ×1.3 (quy mô)
    #   là TÍNH HAI LẦN cùng một thứ — 150 triệu thành 253 triệu.
    is_project_specific: bool = False


@dataclass
class PriceQuote:
    """Kết quả định giá hoàn chỉnh — mọi con số kèm cách suy ra."""

    anchor: PriceAnchor
    complexity: str
    complexity_factor: Decimal
    complexity_reason: str
    scale: str
    scale_factor: Decimal
    scale_reason: str
    rush_factor: Decimal
    rush_reason: str

    suggested: Decimal
    range_min: Decimal
    range_max: Decimal

    line_items: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor": {
                "value": int(self.anchor.value),
                "confidence": self.anchor.confidence,
                "source": self.anchor.source,
                "sample_size": self.anchor.sample_size,
            },
            "factors": [
                {
                    "key": "complexity",
                    "label": "Độ phức tạp",
                    "level": self.complexity,
                    "factor": float(self.complexity_factor),
                    "reason": self.complexity_reason,
                    "decided_by": "ai",
                },
                {
                    "key": "scale",
                    "label": "Quy mô",
                    "level": self.scale,
                    "factor": float(self.scale_factor),
                    "reason": self.scale_reason,
                    "decided_by": "ai",
                },
                {
                    "key": "rush",
                    "label": "Độ gấp",
                    "level": _rush_level(self.rush_factor),
                    "factor": float(self.rush_factor),
                    "reason": self.rush_reason,
                    # Nhãn này lên tới giao diện: người dùng thấy rõ dòng nào máy tính,
                    # dòng nào AI phán.
                    "decided_by": "code",
                },
            ],
            "suggested": int(self.suggested),
            "range_min": int(self.range_min),
            "range_max": int(self.range_max),
            "line_items": self.line_items,
            "warnings": self.warnings,
        }


def _rush_level(factor: Decimal) -> str:
    if factor >= RUSH_FACTOR_URGENT:
        return "urgent"
    if factor >= RUSH_FACTOR_TIGHT:
        return "tight"
    return "normal"


def build_anchor(
    *,
    same_category_values: list[Decimal],
    any_category_values: list[Decimal],
    market_low: Decimal | None,
    market_high: Decimal | None,
) -> PriceAnchor | None:
    """Chọn mốc neo theo thứ tự ưu tiên: dữ liệu THẬT trước, AI đoán sau cùng.

    Dùng TRUNG VỊ chứ không phải trung bình. Nghề freelance đầy giá ngoại lai: 5 deal 30
    triệu lẫn 1 deal 500 triệu thì trung bình ra 108 triệu — sai hoàn toàn. Trung vị ra 30
    triệu, đúng thực tế. Trung vị miễn nhiễm với ngoại lai, trung bình thì không.  #Huynh
    """
    # Bậc 1 — deal đã chốt, CÙNG nhóm dịch vụ. Lọc theo nhóm chính là lời giải cho chuyện
    # "một freelancer làm nhiều nghề": lịch sử thiết kế không dùng để báo giá lập trình.
    if len(same_category_values) >= MIN_DEALS_FOR_HIGH_CONFIDENCE:
        return PriceAnchor(
            value=Decimal(median(same_category_values)),
            confidence="high",
            source=f"Trung vị {len(same_category_values)} dự án cùng nhóm bạn đã chốt",
            sample_size=len(same_category_values),
        )

    if same_category_values:
        return PriceAnchor(
            value=Decimal(median(same_category_values)),
            confidence="medium",
            source=f"Trung vị {len(same_category_values)} dự án cùng nhóm bạn đã chốt",
            sample_size=len(same_category_values),
        )

    # Bậc 2 — nới điều kiện: mọi deal đã chốt, bất kể nhóm. Kém chính xác hơn (giá thiết kế
    # khác giá lập trình), nhưng vẫn là TIỀN THẬT bạn từng thu được.
    if any_category_values:
        return PriceAnchor(
            value=Decimal(median(any_category_values)),
            confidence="medium",
            source=f"Trung vị {len(any_category_values)} dự án bạn đã chốt (mọi nhóm)",
            sample_size=len(any_category_values),
        )

    # Bậc 3 — chưa chốt deal nào. Rơi về giá thị trường AI ước lúc chấm điểm.
    if market_low and market_high and market_low > 0:
        return PriceAnchor(
            value=(market_low + market_high) / 2,
            confidence="low",
            source="AI ước lượng giá thị trường — bạn chưa có dự án nào đã chốt để đối chiếu",
            sample_size=0,
            is_project_specific=True,
        )

    # Không neo được vào đâu cả. Trả None và để tầng trên nói thật với người dùng, thay vì
    # bịa một con số.
    return None


# Bóc ngày ra khỏi câu tiếng Việt tự do.
#
# `deals.desired_timeline` là String(255), không phải cột ngày — khách viết "trước
# 30/09/2026", "trong 6 tuần", "gấp lắm". Muốn tính độ gấp BẰNG CODE thì phải bóc được một
# ngày thật ra khỏi đó.
#
# Cố ý KHÔNG nhờ AI bóc: đây là việc máy làm được tuyệt đối chính xác và kiểm chứng được
# bằng unit test. Không bóc được thì trả None và KHÔNG tính phụ phí gấp — thà bỏ sót còn
# hơn tính thêm tiền của khách vì một cái regex đoán mò.  #Huynh
_DATE_PATTERNS = (
    re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})"),  # 30/09/2026
    re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})"),  # 2026-09-30 (ISO)
)
_RELATIVE_PATTERN = re.compile(r"(\d{1,2})\s*(ngày|tuần|tháng)", re.IGNORECASE)
_RELATIVE_DAYS = {"ngày": 1, "tuần": 7, "tháng": 30}


def parse_deadline(text: str | None, today: date | None = None) -> date | None:
    """Bóc hạn bàn giao ra khỏi chuỗi tiếng Việt tự do. Không chắc thì trả None."""
    if not text:
        return None

    now = today or date.today()

    for index, pattern in enumerate(_DATE_PATTERNS):
        match = pattern.search(text)
        if not match:
            continue
        try:
            if index == 0:
                day, month, year = (int(g) for g in match.groups())
            else:
                year, month, day = (int(g) for g in match.groups())
            return date(year, month, day)
        except ValueError:
            # "32/13/2026" — khách gõ nhầm. Bỏ qua, đừng nổ.
            continue

    match = _RELATIVE_PATTERN.search(text)
    if match:
        amount, unit = int(match.group(1)), match.group(2).lower()
        return now + timedelta(days=amount * _RELATIVE_DAYS[unit])

    return None


def rush_factor_from_deadline(
    deadline: date | None, today: date | None = None
) -> tuple[Decimal, str]:
    """Độ gấp — TÍNH BẰNG CODE từ hạn khách nêu, không hỏi AI.

    Trả về ``(hệ_số, lý_do)``. Lý do luôn nêu con số ngày cụ thể để người dùng tự kiểm.
    """
    if deadline is None:
        return RUSH_FACTOR_NORMAL, "Khách chưa nêu hạn bàn giao — không tính phụ phí gấp."

    days = (deadline - (today or date.today())).days

    if days < 0:
        return (
            RUSH_FACTOR_URGENT,
            f"Hạn khách nêu ({deadline:%d/%m/%Y}) ĐÃ QUA — cần thống nhất lại thời gian.",
        )
    if days <= RUSH_URGENT_DAYS:
        return (
            RUSH_FACTOR_URGENT,
            f"Chỉ còn {days} ngày tới hạn {deadline:%d/%m/%Y} — rất gấp, phải gạt việc khác.",
        )
    if days <= RUSH_TIGHT_DAYS:
        return (
            RUSH_FACTOR_TIGHT,
            f"Còn {days} ngày tới hạn {deadline:%d/%m/%Y} — khá gấp.",
        )
    return (
        RUSH_FACTOR_NORMAL,
        f"Còn {days} ngày tới hạn {deadline:%d/%m/%Y} — thời gian thoải mái.",
    )


def _round_money(value: Decimal) -> Decimal:
    """Làm tròn lên bội của 500.000 ₫, tối thiểu 500.000 ₫."""
    if value <= 0:
        return ROUND_TO
    steps = (value / ROUND_TO).to_integral_value(rounding="ROUND_HALF_UP")
    return max(ROUND_TO, Decimal(steps) * ROUND_TO)


def compute_quote(
    *,
    anchor: PriceAnchor,
    complexity: str,
    complexity_reason: str,
    scale: str,
    scale_reason: str,
    deadline: date | None,
    weights: list[dict[str, Any]] | None = None,
    client_budget: Decimal | None = None,
    today: date | None = None,
) -> PriceQuote:
    """Nhân mốc neo với 3 hệ số, nới thành khoảng, chia hạng mục.

    `complexity` / `scale` do AI chấm (rời rạc). Giá trị lạ thì rơi về "normal" — không tin
    model tự giữ luật, và một hệ số lạ lọt vào phép nhân là sai tiền thật.
    """
    r_factor, r_reason = rush_factor_from_deadline(deadline, today)

    if anchor.is_project_specific:
        # Mốc neo ĐÃ là giá riêng cho dự án này -> KHÔNG nhân hệ số nữa, nếu không là tính
        # hai lần. Nhưng vẫn giữ nguyên nhận xét của AI để người dùng đọc — chỉ là hệ số
        # bằng 1.  #Huynh
        c_factor = Decimal("1.0")
        s_factor = Decimal("1.0")
        note = (
            " (không nhân thêm: giá thị trường AI ước đã tính tới yếu tố này của chính dự "
            "án này)"
        )
        complexity_reason = (complexity_reason or "").strip() + note
        scale_reason = (scale_reason or "").strip() + note
    else:
        c_factor = COMPLEXITY_FACTORS.get(complexity, COMPLEXITY_FACTORS["normal"])
        s_factor = SCALE_FACTORS.get(scale, SCALE_FACTORS["normal"])

    raw = anchor.value * c_factor * s_factor * r_factor
    suggested = _round_money(raw)

    spread = RANGE_SPREAD[anchor.confidence]
    range_min = _round_money(suggested * (Decimal("1") - spread))
    range_max = _round_money(suggested * (Decimal("1") + spread))

    warnings: list[str] = []

    # Đối chiếu ngân sách khách — CHỈ CẢNH BÁO, không tự hạ giá cho vừa túi khách. Quyết
    # định nhận hay bỏ deal dưới giá là của freelancer, không phải của phần mềm.  #Huynh
    if client_budget and client_budget > 0:
        if suggested > client_budget * Decimal("1.2"):
            over = int((suggested / client_budget - 1) * 100)
            warnings.append(
                f"Giá đề xuất cao hơn ngân sách khách nêu {over}% "
                f"({int(client_budget):,} ₫) — nguy cơ mất deal. Cân nhắc thu hẹp phạm vi "
                f"thay vì hạ giá.".replace(",", ".")
            )
        elif suggested < client_budget * Decimal("0.8"):
            warnings.append(
                f"Khách nêu ngân sách {int(client_budget):,} ₫ — cao hơn giá đề xuất. "
                f"Bạn còn dư địa nâng giá.".replace(",", ".")
            )

    if anchor.confidence == "low":
        warnings.append(
            "Chưa có dự án nào đã chốt để neo giá, nên khoảng này chỉ là ước lượng. "
            "Chốt xong deal đầu tiên, hệ thống sẽ neo vào giá thật của bạn."
        )

    return PriceQuote(
        anchor=anchor,
        complexity=complexity if complexity in COMPLEXITY_FACTORS else "normal",
        complexity_factor=c_factor,
        complexity_reason=complexity_reason,
        scale=scale if scale in SCALE_FACTORS else "normal",
        scale_factor=s_factor,
        scale_reason=scale_reason,
        rush_factor=r_factor,
        rush_reason=r_reason,
        suggested=suggested,
        range_min=range_min,
        range_max=range_max,
        line_items=split_line_items(suggested, weights),
        warnings=warnings,
    )


def split_line_items(total: Decimal, weights: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Chia tổng thành hạng mục theo TỈ TRỌNG CÔNG SỨC (%), KHÔNG theo số giờ.

    Vì sao không dùng giờ: số giờ do freelancer tự khai (hoặc AI tự đoán) nên vô nghĩa, mà
    lộ giờ ra cho khách là mời họ mặc cả từng giờ ("sao thiết kế tới 16 tiếng?"). Khách mua
    KẾT QUẢ, không mua thời gian của bạn.

    AI chỉ phán CÔNG SỨC TƯƠNG ĐỐI giữa các hạng mục — việc nó làm tốt — còn tiền thì chia
    bằng code. Tỉ trọng được chuẩn hoá về đúng 100%, và đồng lẻ do làm tròn được dồn vào
    hạng mục cuối để tổng các dòng KHỚP TUYỆT ĐỐI với tổng báo giá. Bảng cộng không ra tổng
    là thứ khách sẽ soi ra ngay.  #Huynh
    """
    if not weights:
        return []

    cleaned = [
        (str(w.get("label") or "").strip(), max(0, int(w.get("weight") or 0)))
        for w in weights
        if str(w.get("label") or "").strip()
    ]
    cleaned = [(label, weight) for label, weight in cleaned if weight > 0]
    if not cleaned:
        return []

    total_weight = sum(weight for _, weight in cleaned)
    items: list[dict[str, Any]] = []
    allocated = Decimal(0)

    for index, (label, weight) in enumerate(cleaned):
        if index == len(cleaned) - 1:
            amount = total - allocated  # dồn phần lẻ vào dòng cuối
        else:
            amount = _round_money(total * Decimal(weight) / Decimal(total_weight))
            allocated += amount

        items.append(
            {
                "label": label,
                "weight_percent": round(weight / total_weight * 100),
                "amount": int(amount),
            }
        )

    return items
