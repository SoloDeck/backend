"""Chuyển `proposal.content` (JSONB) thành ProposalDocument để render PDF.

Vì sao cần file này: `content` được khai là `dict` trần nên backend KHÔNG validate
gì cả, và thực tế đang có HAI shape cùng tồn tại trong DB:

1. **ProposalContentDTO** — shape CHÍNH THỨC trong `contracts/openapi.yaml`, và là
   thứ frontend lưu mỗi khi người dùng sửa báo giá:
   ``{title, executive_summary, scope_of_work: str, timeline: {...}, pricing: {...},
   terms: {payment_terms}, notes}``

2. **Shape nội bộ của AI** — `/proposals/ai-generate` lưu thẳng output của model:
   ``{project_overview, scope_of_work: list, deliverables, timeline: str,
   pricing: str, payment_terms, assumptions}``

Bản cũ của `generate_pdf` index cứng bằng ``content["project_overview"]`` — tức là
chỉ đọc được shape (2), và dùng ``[...]`` chứ không ``.get()`` nên thiếu MỘT khoá là
`KeyError` → **500**. Kết quả: mọi báo giá do frontend tạo/sửa đều không xuất được
PDF, dù frontend làm ĐÚNG hợp đồng.

Ở đây ta đọc được cả hai, ưu tiên shape của hợp đồng, và dùng `.get()` khắp nơi để
thiếu dữ liệu thì để trống chứ không nổ.  #Huynh
"""

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Any

from src.ai.proposal_generator.schemas.proposal_document import (
    PaymentMilestone,
    PricingLineItem,
    ProposalDocument,
)

# Thời điểm thu của một hạng mục — LOẠI có sẵn, không phải chữ tự do.
#
# Vì sao là enum: bản đầu để freelancer gõ chữ, và hệ thống phải ĐOÁN xem câu đó có nghĩa "thu
# trước" không bằng cách dò từ khoá tiếng Việt ("khi ký", "đặt cọc"...). Gõ "Ngay sau khi hai
# bên xác nhận" là đoán trượt, cảnh báo hiện sai. Chữ đẹp cho khách đọc nhưng máy không suy
# luận được gì trên nó.
#
# Chữ tự do KHÔNG mất: nó chuyển sang `due_note`, in đè lên nhãn mặc định. Hợp đồng thật hay
# có điều kiện riêng ("khi bên A duyệt bản demo"), ép về hai câu cố định là làm nghèo tờ giấy.
DUE_ON_SIGNING = "on_signing"
DUE_ON_COMPLETION = "on_completion"

DUE_TYPE_LABELS = {
    DUE_ON_SIGNING: "Khi ký hợp đồng",
    DUE_ON_COMPLETION: "Khi hoàn thành hạng mục",
}
DEFAULT_COST_ITEM_DUE = DUE_TYPE_LABELS[DUE_ON_COMPLETION]

# Từ khoá nhận ra "thu trước khi làm" trong dữ liệu CŨ (khi thời điểm thu còn là chữ tự do).
# CHỈ dùng làm cầu nối đọc dữ liệu cũ — đừng gọi nó ở đường ghi mới.  #Huynh
_LEGACY_UPFRONT_HINTS = ("khi ký", "ký hợp đồng", "trước khi", "đặt cọc", "tạm ứng", "ứng trước")


@dataclass(frozen=True)
class CostItem:
    """Một hạng mục chi phí ở mục 7, đã quy về SỐ NGUYÊN đồng.

    Đây là ĐƠN VỊ THU TIỀN của hệ thống: mỗi hạng mục sinh ra một task thu tiền và một hoá
    đơn. Nên `amount` phải là con số chốt để tính toán được, không phải chuỗi đã format —
    `PricingLineItem` (chuỗi "76.000.000 VND") chỉ dành cho tầng render.

    `due_type` là thứ MÁY đọc (thu trước hay thu khi xong), `due_note` là thứ KHÁCH đọc.
    """

    label: str
    amount: int
    due_type: str = DUE_ON_COMPLETION
    due_note: str = ""
    currency: str = "VND"

    @property
    def due_label(self) -> str:
        """Chữ in ra tờ báo giá: ghi chú riêng nếu có, không thì nhãn chuẩn của loại."""
        return self.due_note or DUE_TYPE_LABELS.get(self.due_type, DEFAULT_COST_ITEM_DUE)

    @property
    def collected_upfront(self) -> bool:
        return self.due_type == DUE_ON_SIGNING


def _text(value: Any) -> str:
    """Ép về chuỗi; None thành rỗng.  #Huynh"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value)


def _text_list(value: Any) -> list[str]:
    """Ép về danh sách chuỗi.

    `scope_of_work` là `list` ở shape AI nhưng là `str` (nhiều dòng) ở shape hợp
    đồng — nên phải nhận cả hai.  #Huynh
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    return [_text(value)]


def _money(amount: Any, currency: str) -> str:
    """Định dạng tiền theo kiểu Việt Nam: 30.000.000 VND.  #Huynh"""
    try:
        return f"{int(float(amount)):,}".replace(",", ".") + (f" {currency}" if currency else "")
    except (TypeError, ValueError):
        return _text(amount)


def _pricing_to_text(value: Any) -> str:
    """Shape hợp đồng cho `pricing` là object; shape AI là chuỗi. Nhận cả hai.  #Huynh"""
    if not isinstance(value, dict):
        return _text(value)

    currency = _text(value.get("currency")) or "VND"
    lines: list[str] = []

    for item in value.get("line_items") or []:
        if not isinstance(item, dict):
            lines.append(_text(item))
            continue
        desc = _text(item.get("description"))
        amount = item.get("amount")
        lines.append(f"{desc}: {_money(amount, currency)}" if amount is not None else desc)

    total = value.get("total")
    if total is not None:
        lines.append(f"Tổng cộng: {_money(total, currency)}")

    return "\n".join(line for line in lines if line)


def _resolve_total_int(content: dict[str, Any]) -> int:
    """Tổng báo giá (giá đã chốt) dưới dạng int > 0, hoặc 0 nếu chưa có.

    Ưu tiên `pricing_detail.final_price` → `suggested` → `pricing.total` (shape DTO).  #Huynh"""
    detail = content.get("pricing_detail")
    if isinstance(detail, dict):
        for key in ("final_price", "suggested"):
            try:
                value = int(detail.get(key) or 0)
            except (TypeError, ValueError):
                value = 0
            if value > 0:
                return value
    pricing = content.get("pricing")
    if isinstance(pricing, dict) and pricing.get("total") is not None:
        try:
            value = int(pricing["total"])
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    return 0


def infer_due_type(text: str) -> str | None:
    """Suy thời điểm thu từ một câu tiếng Việt. `None` = không đoán được.

    ĐÂY LÀ CẦU NỐI CHO DỮ LIỆU CŨ, không phải cách làm việc chính. Dùng ở hai chỗ: đọc báo giá
    còn ghi thời điểm thu bằng chữ tự do, và sinh task từ mốc thanh toán % của báo giá cũ.
    Đường ghi mới luôn có `due_type` hẳn hoi nên không đi qua đây.

    Đoán trượt chỉ mất một nhãn trên bảng việc, không sai tiền — nên thà trả `None` (giao diện
    im lặng) còn hơn đoán bừa một loại rồi nhắc sai.  #Huynh
    """
    lowered = (text or "").lower()
    if not lowered:
        return None
    if any(hint in lowered for hint in _LEGACY_UPFRONT_HINTS):
        return DUE_ON_SIGNING
    if any(hint in lowered for hint in ("hoàn thành", "nghiệm thu", "bàn giao")):
        return DUE_ON_COMPLETION
    return None


def _coerce_due(item: dict[str, Any]) -> tuple[str | None, str]:
    """``(due_type, due_note)`` của một hạng mục. `due_type` là `None` khi chưa ai đặt."""
    raw_type = _text(item.get("due_type")).lower()
    if raw_type in DUE_TYPE_LABELS:
        return raw_type, _text(item.get("due_note"))

    legacy = _text(item.get("due_note") or item.get("due"))
    if not legacy:
        return None, ""
    # Ghi chú trùng y hệt nhãn chuẩn thì bỏ đi — in lại nguyên câu mặc định là thừa.
    note = "" if legacy in DUE_TYPE_LABELS.values() else legacy
    return infer_due_type(legacy), note


def _typed_cost_items(override: list[Any]) -> list[CostItem]:
    """Bóc dạng MỚI ``[{"label", "amount", "due_type"?, "due_note"?}]``. Rỗng = không phải dạng này.

    Chỉ nhận khi **mọi** phần tử đều là dict có nhãn — nửa nọ nửa kia thì trả rỗng để chỗ gọi
    rơi về dạng cũ, thay vì dựng một bảng lắp ghép từ hai nguồn.

    Tiền thiếu/hỏng tính là 0 chứ không loại bỏ dòng: mất hẳn một hạng mục khỏi báo giá gửi
    khách nguy hiểm hơn nhiều so với một dòng ghi 0đ mà freelancer nhìn thấy và sửa.

    MẶC ĐỊNH GIỮ CỌC: chưa dòng nào được đặt loại thì dòng ĐẦU thành "khi ký hợp đồng". Bản
    trước mặc định tất cả là "khi hoàn thành" — tức là freelancer làm xong sạch dự án mới nhận
    đồng đầu tiên, TỆ HƠN hẳn lịch 50/50 của bản cũ. Freelancer đặt tay dòng nào thì tôn trọng
    hết, không đè.  #Huynh
    """
    if not all(isinstance(item, dict) for item in override):
        return []

    parsed: list[tuple[str, int, str | None, str]] = []
    for item in override:
        label = _text(item.get("label") or item.get("description"))
        if not label:
            return []
        try:
            amount = int(Decimal(str(item.get("amount") or 0)))
        except (TypeError, ValueError, InvalidOperation):
            amount = 0
        due_type, due_note = _coerce_due(item)
        parsed.append((label, max(amount, 0), due_type, due_note))

    nobody_chose = all(due_type is None for _, _, due_type, _ in parsed)
    return [
        CostItem(
            label=label,
            amount=amount,
            due_type=due_type
            or (DUE_ON_SIGNING if nobody_chose and index == 0 else DUE_ON_COMPLETION),
            due_note=due_note,
        )
        for index, (label, amount, due_type, due_note) in enumerate(parsed)
    ]


def typed_pricing_items(override: list[Any]) -> list[tuple[str, int]]:
    """Vỏ mỏng giữ nguyên chữ ký cũ ``[(nhãn, tiền)]`` cho các chỗ gọi chưa cần thời điểm thu."""
    return [(item.label, item.amount) for item in _typed_cost_items(override)]


def _with_deposit_default(items: list[CostItem]) -> list[CostItem]:
    """Dòng ĐẦU thu khi ký hợp đồng — dùng cho các bảng SUY RA (bộ định giá, shape DTO), nơi
    chưa ai kịp chọn thời điểm thu.

    Không có bước này thì mặc định là "thu khi hoàn thành" cho tất cả, tức freelancer làm xong
    sạch dự án mới nhận đồng đầu tiên — tệ hơn hẳn lịch 50/50 của bản cũ. Freelancer vẫn đổi
    được từng dòng ở màn soạn báo giá.  #Huynh"""
    if not items:
        return items
    first = items[0]
    return [replace(first, due_type=DUE_ON_SIGNING), *items[1:]]


def _resolve_cost_items_with_total(content: dict[str, Any]) -> tuple[list[CostItem], int | None]:
    """Chuỗi tìm hạng mục chi phí, theo ĐÚNG thứ tự ưu tiên. Phần tử thứ hai là tổng ĐÈ
    (chỉ shape DTO mới có tổng khai riêng, có thể khác tổng các dòng); `None` = cộng các dòng.

    Bốn nguồn, xét lần lượt:

    1. ``pricing_items`` dạng typed — freelancer tự gõ tiền ở màn review. Dùng thẳng.
    2. ``pricing_items`` chỉ có nhãn (bản nháp cũ) — chia đều giá chốt.
    3. ``pricing_detail.line_items`` — bảng của bộ định giá, rescale về giá chốt.
    4. ``pricing.line_items`` (shape DTO) — bảng đã có sẵn tiền.

    Vì sao phải là MỘT hàm: tờ báo giá gửi khách và bộ sinh task thu tiền đều đọc từ đây.
    Hai chuỗi tìm riêng là ngày nào đó khách cầm bảng ghi bốn dòng mà nhận về ba hoá đơn số
    khác — đúng loại lệch mà cả module này sinh ra để chặn.  #Huynh
    """
    override = content.get("pricing_items")
    if isinstance(override, list) and override:
        typed = _typed_cost_items(override)
        if typed:
            return typed, None

        labels = [_text(x) for x in override if _text(x)]
        total_int = _resolve_total_int(content)
        if labels and total_int > 0:
            items: list[CostItem] = []
            allocated = 0
            n = len(labels)
            for index, label in enumerate(labels):
                if index == n - 1:
                    amount = total_int - allocated  # dồn phần lẻ vào dòng cuối
                else:
                    amount = round(total_int / n / 1000) * 1000
                    allocated += amount
                items.append(CostItem(label=label, amount=amount))
            return _with_deposit_default(items), total_int

    detail = content.get("pricing_detail")
    if isinstance(detail, dict):
        raw_items = detail.get("line_items") or []
        suggested = detail.get("suggested") or 0
        total = detail.get("final_price") or suggested

        try:
            total_int = int(total)
            suggested_int = int(suggested)
        except (TypeError, ValueError):
            total_int, suggested_int = 0, 0

        if raw_items and suggested_int > 0 and total_int > 0:
            items = []
            allocated = 0
            ratio = total_int / suggested_int
            cleaned = [it for it in raw_items if isinstance(it, dict)]
            for index, it in enumerate(cleaned):
                if index == len(cleaned) - 1:
                    amount = total_int - allocated  # dồn phần lẻ vào dòng cuối
                else:
                    base = int(it.get("amount") or 0) * ratio
                    amount = round(base / 1000) * 1000
                    allocated += amount
                items.append(
                    CostItem(
                        label=_text(it.get("label") or it.get("description")),
                        amount=amount,
                    )
                )
            if items:
                return _with_deposit_default(items), total_int

    # Shape hợp đồng (DTO): pricing là object có line_items sẵn.
    pricing = content.get("pricing")
    if isinstance(pricing, dict) and pricing.get("line_items"):
        currency = _text(pricing.get("currency")) or "VND"
        items = []
        for it in pricing["line_items"]:
            if not isinstance(it, dict):
                continue
            try:
                amount = int(Decimal(str(it.get("amount") or 0)))
            except (TypeError, ValueError, InvalidOperation):
                amount = 0
            items.append(
                CostItem(
                    label=_text(it.get("description")),
                    amount=max(amount, 0),
                    currency=currency,
                )
            )
        if items:
            # Tổng ở shape DTO khai RIÊNG và có thể khác tổng các dòng — in đúng thứ đang có.
            raw_total = pricing.get("total")
            try:
                declared = int(Decimal(str(raw_total))) if raw_total is not None else None
            except (TypeError, ValueError, InvalidOperation):
                declared = None
            return _with_deposit_default(items), declared

    return [], None


def resolve_cost_items(content: dict[str, Any]) -> list[CostItem]:
    """Hạng mục chi phí của một báo giá — nguồn DUY NHẤT cho cả tờ báo giá lẫn task thu tiền."""
    items, _ = _resolve_cost_items_with_total(content or {})
    return items


def _structured_pricing(content: dict[str, Any]) -> tuple[list[PricingLineItem], str, str]:
    """Bảng giá có cấu trúc cho template. Trả về ``(line_items, tổng, chuỗi_dự_phòng)``.

    Chỉ là lớp ĐỊNH DẠNG mỏng trên `_resolve_cost_items_with_total` — mọi quyết định "hạng
    mục là gì, bao nhiêu tiền" nằm ở đó, dùng chung với bộ sinh task thu tiền.

    KHÔNG ép tổng các dòng phải bằng giá chào ở đây: `ProposalsService.transition_status`
    mới là chỗ chặn gửi khi lệch. Tầng render vẽ trung thực thứ đang có, để freelancer nhìn
    thấy chỗ lệch mà sửa.  #Huynh
    """
    items, declared_total = _resolve_cost_items_with_total(content)
    if items:
        currency = items[0].currency
        # Shape DTO khai tổng riêng (có thể đã gồm thuế) → in đúng con số đã khai. Không khai
        # thì cộng các dòng: bản cũ để TRỐNG dòng tổng, mà một bảng có dòng nhưng không có
        # tổng thì khách phải tự cộng — và con số cộng ra không thể mâu thuẫn với bảng.  #Huynh
        total = declared_total if declared_total is not None else sum(i.amount for i in items)
        return (
            [
                PricingLineItem(
                    description=i.label,
                    amount=_money(i.amount, i.currency),
                    due=i.due_label,
                )
                for i in items
            ],
            _money(total, currency),
            "",
        )

    # Không có bảng: rơi về chuỗi (báo giá cũ, hoặc AI trả chuỗi "Giá sẽ báo sau...").
    return [], "", _pricing_to_text(content.get("pricing"))


def _timeline_to_text(value: Any) -> str:
    """Shape hợp đồng cho `timeline` là object (mốc thời gian); shape AI là chuỗi.  #Huynh"""
    if not isinstance(value, dict):
        return _text(value)

    lines: list[str] = []
    start, end = _text(value.get("start_date")), _text(value.get("end_date"))
    if start or end:
        lines.append(" – ".join(part for part in (start, end) if part))

    for milestone in value.get("milestones") or []:
        if not isinstance(milestone, dict):
            lines.append(_text(milestone))
            continue
        title = _text(milestone.get("title"))
        due = _text(milestone.get("due_date"))
        lines.append(f"{title} ({due})" if title and due else title or due)

    return "\n".join(line for line in lines if line)


def extract_payment_milestones(content: dict[str, Any]) -> list[PaymentMilestone]:
    """Trích các đợt thanh toán có cấu trúc, nhận cả shape AI (`payment_milestones`) lẫn
    shape DTO (`terms.payment_schedule`). Entry hỏng thì bỏ qua, không nổ.

    Public vì Stage 2 dùng lại chính nguồn này để SINH TASK "Thu tiền" khi báo giá được
    chốt — task và bảng mốc trên PDF phải khớp nhau tuyệt đối.  #Huynh"""
    raw = content.get("payment_milestones")
    if raw is None:
        terms = content.get("terms")
        if isinstance(terms, dict):
            raw = terms.get("payment_schedule") or terms.get("payment_milestones")
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []

    out: list[PaymentMilestone] = []
    for entry in raw:
        if isinstance(entry, str):
            if entry.strip():
                out.append(PaymentMilestone(label=entry.strip()))
            continue
        if not isinstance(entry, dict):
            continue
        label = _text(
            entry.get("label")
            or entry.get("description")
            or entry.get("name")
            or entry.get("stage")
        )
        if not label:
            continue
        raw_percent = entry.get("percent", entry.get("percentage"))
        try:
            percent = (
                int(float(str(raw_percent).strip().rstrip("%")))
                if raw_percent not in (None, "")
                else None
            )
        except (TypeError, ValueError):
            percent = None
        amount = _text(entry.get("amount") or entry.get("value"))
        due = _text(
            entry.get("due")
            or entry.get("when")
            or entry.get("condition")
            or entry.get("timing")
            or entry.get("date")
        )
        out.append(PaymentMilestone(label=label, percent=percent, amount=amount, due=due))
    return out


def build_proposal_document(
    content: dict[str, Any],
    *,
    freelancer_name: str,
    client_name: str,
    company_name: str | None,
    project_type: str,
    proposal_date: str,
    freelancer_email: str = "",
    freelancer_phone: str = "",
    client_email: str = "",
    client_phone: str = "",
    valid_until: str = "",
) -> ProposalDocument:
    """Dựng ProposalDocument từ `content` bất kể nó theo shape nào.  #Huynh"""
    content = content or {}

    # Ưu tiên shape của hợp đồng (executive_summary), rồi mới tới shape AI
    # (project_overview), cuối cùng là title.
    overview = (
        _text(content.get("executive_summary"))
        or _text(content.get("project_overview"))
        or _text(content.get("title"))
    )

    raw_terms = content.get("terms")
    terms: dict[str, Any] = raw_terms if isinstance(raw_terms, dict) else {}
    payment_terms = _text(content.get("payment_terms")) or _text(terms.get("payment_terms"))

    # `notes` (hợp đồng) và `assumptions` (AI) đóng cùng vai trò: ghi chú thêm.
    assumptions = _text(content.get("assumptions")) or _text(content.get("notes"))

    line_items, pricing_total, pricing_fallback = _structured_pricing(content)

    return ProposalDocument(
        freelancer_name=freelancer_name,
        freelancer_email=freelancer_email,
        freelancer_phone=freelancer_phone,
        client_name=client_name,
        client_email=client_email,
        client_phone=client_phone,
        company_name=company_name,
        project_type=project_type,
        proposal_date=proposal_date,
        valid_until=valid_until,
        project_overview=overview,
        scope_of_work=_text_list(content.get("scope_of_work")),
        deliverables=_text_list(content.get("deliverables")),
        timeline=_timeline_to_text(content.get("timeline")),
        pricing_line_items=line_items,
        pricing_total=pricing_total,
        pricing=pricing_fallback,
        payment_terms=payment_terms,
        # CHỈ dành cho báo giá CŨ. Từ khi gộp mục 7 và 8, thời điểm thu đi kèm ngay trên từng
        # dòng chi phí (`PricingLineItem.due`); template chỉ dựng bảng mốc % khi KHÔNG có hạng
        # mục nào — tức là bản nháp cũ trong DB.  #Huynh
        payment_milestones=extract_payment_milestones(content),
        assumptions=assumptions,
        out_of_scope=_text_list(content.get("out_of_scope")),
        revision_policy=_text(content.get("revision_policy"))
        or _text(terms.get("revision_policy")),
        standard_terms=_text(content.get("standard_terms")),
    )
