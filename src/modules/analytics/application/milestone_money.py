"""Tiền theo MỐC THANH TOÁN — nguồn số liệu cho bảng doanh thu.

Vì sao tồn tại: bảng doanh thu vốn chỉ đếm hoá đơn (`SUM(invoices.total)`), trong khi từ
Phase B luồng chính không còn bắt buộc lập hoá đơn — freelancer theo dõi thu tiền bằng các
task "Thu tiền:" sinh ra từ mốc thanh toán của báo giá đã chốt. Hậu quả đo được trên bản
chạy thật: phễu hiện 7 deal đang triển khai trị giá 1,24 tỷ, còn bảng doanh thu ghi "Còn
phải thu: 0 đ". Màn hình bảo freelancer không còn gì để thu trong khi thực tế còn hơn một tỷ.

Đây là hàm THUẦN (không I/O) để test được mà không cần DB, và để đúng MỘT nơi định nghĩa
"tiền của một mốc là bao nhiêu" — dùng chung nguồn `extract_payment_milestones` với bảng in
trên PDF và với bộ sinh task, nên ba chỗ không bao giờ hiểu khác nhau.  #Huynh
"""

from dataclasses import dataclass
from decimal import Decimal

from src.ai.proposal_generator.schemas.proposal_document import PaymentMilestone
from src.modules.tasks.application.service import PAYMENT_TASK_PREFIX


@dataclass(frozen=True)
class MilestoneMoney:
    label: str
    amount: Decimal
    collected: bool


def task_title_for(label: str) -> str:
    """Tên task mà bộ sinh task đặt cho một mốc — khớp tuyệt đối với `_milestones_to_payloads`."""
    return f"{PAYMENT_TASK_PREFIX} {label}"[:500]


def split_milestone_amounts(
    milestones: list[PaymentMilestone], total: Decimal
) -> list[Decimal]:
    """Chia `total` cho từng mốc theo %.

    Mốc nào KHÔNG khai `percent` thì chia đều phần trăm còn lại cho chúng — hợp đồng thật
    hay có kiểu "50% khi ký, phần còn lại khi bàn giao", bỏ qua mốc không có % là mất tiền
    khỏi bảng mà không ai biết.

    Đồng lẻ do làm tròn dồn vào mốc CUỐI để tổng các mốc khớp tuyệt đối với giá chốt — cùng
    quy tắc với bảng chi phí in trên báo giá.  #Huynh
    """
    if not milestones or total <= 0:
        return [Decimal(0) for _ in milestones]

    with_percent = [m.percent for m in milestones]
    known = sum(p for p in with_percent if p is not None)
    missing = [i for i, p in enumerate(with_percent) if p is None]
    share_for_missing = (
        max(Decimal(0), Decimal(100) - Decimal(known)) / len(missing)
        if missing
        else Decimal(0)
    )

    amounts: list[Decimal] = []
    for percent in with_percent:
        ratio = Decimal(percent) if percent is not None else share_for_missing
        amounts.append((total * ratio / Decimal(100)).quantize(Decimal("1")))

    # Dồn phần lệch vào mốc cuối, chỉ khi tổng % đúng bằng 100 (không tự ý "sửa" hợp đồng
    # ghi 130% thành 100% — bảng phải phản ánh thứ đã ký, kể cả khi nó sai).
    total_percent = Decimal(known) + share_for_missing * len(missing)
    if total_percent == 100:
        amounts[-1] += total - sum(amounts)
    return amounts


def milestone_money_for_deal(
    *,
    final_price: Decimal | None,
    milestones: list[PaymentMilestone],
    done_task_titles: set[str],
) -> list[MilestoneMoney]:
    """Tiền từng mốc của MỘT deal + mốc nào đã thu.

    `done_task_titles` là tên các task "Thu tiền:" đã tick xong trên project của deal. Mốc
    không tìm được task tương ứng (dữ liệu cũ, task bị đổi tên) coi như CHƯA THU — thà báo
    thừa "còn phải thu" còn hơn âm thầm coi như đã lấy được tiền.  #Huynh
    """
    total = Decimal(final_price or 0)
    amounts = split_milestone_amounts(milestones, total)
    return [
        MilestoneMoney(
            label=m.label,
            amount=amount,
            collected=task_title_for(m.label) in done_task_titles,
        )
        for m, amount in zip(milestones, amounts, strict=True)
    ]


@dataclass(frozen=True)
class MoneyTotals:
    contracted: Decimal
    collected: Decimal
    outstanding: Decimal
    milestones_pending: int


def totals(rows: list[MilestoneMoney]) -> MoneyTotals:
    collected = sum((r.amount for r in rows if r.collected), Decimal(0))
    outstanding = sum((r.amount for r in rows if not r.collected), Decimal(0))
    return MoneyTotals(
        contracted=collected + outstanding,
        collected=collected,
        outstanding=outstanding,
        milestones_pending=sum(1 for r in rows if not r.collected),
    )
