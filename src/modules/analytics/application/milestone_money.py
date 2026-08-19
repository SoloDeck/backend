"""Tiền theo TASK THU TIỀN — nguồn số liệu cho bảng doanh thu.

Vì sao tồn tại: bảng doanh thu vốn chỉ đếm hoá đơn (`SUM(invoices.total)`), trong khi luồng
chính không bắt buộc lập hoá đơn — freelancer theo dõi thu tiền bằng các task thu tiền sinh ra
từ hạng mục chi phí của báo giá đã chốt. Hậu quả đo được trên bản chạy thật: phễu hiện 7 deal
đang triển khai trị giá 1,24 tỷ, còn bảng doanh thu ghi "Còn phải thu: 0 đ". Màn hình bảo
freelancer không còn gì để thu trong khi thực tế còn hơn một tỷ.

Trước đây file này còn phải CHIA % ra tiền rồi khớp mốc với TÊN TASK, vì số tiền không được
lưu ở đâu cả. Từ khi có `tasks.billing_amount` thì tiền đã nằm sẵn trên task — chỗ này chỉ
còn cộng. Cả `split_milestone_amounts` lẫn `task_title_for` đã bỏ: chúng là hai nửa của phép
khớp-theo-tên, mà khớp theo tên chính là thứ đứt mỗi khi freelancer đổi tên task.

Vẫn là hàm THUẦN (không I/O) để test được mà không cần DB.  #Huynh
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class MilestoneMoney:
    label: str
    amount: Decimal
    collected: bool


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
