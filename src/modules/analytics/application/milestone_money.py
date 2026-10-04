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

import uuid
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class MilestoneMoney:
    label: str
    amount: Decimal
    collected: bool
    # Deal có mốc này. Để đếm được tiền "đã ký" nằm trên BAO NHIÊU deal; bỏ trống (người gọi
    # chỉ cần cộng tiền) thì không tính vào số đó.
    deal_id: uuid.UUID | None = None
    # Mốc thuộc deal KHÔNG THÀNH CÔNG. Chỉ những mốc ĐÃ THU của deal đó mới còn được đưa vào đây
    # (tiền đã nhận là tiền thật); mốc chưa thu thì người gọi bỏ đi trước. Cờ này để loại deal thất
    # bại khỏi "giá trị trung bình mỗi deal".
    lost: bool = False


@dataclass(frozen=True)
class MoneyTotals:
    contracted: Decimal
    collected: Decimal
    outstanding: Decimal
    milestones_pending: int
    # Số deal KHÁC NHAU đã có task thu tiền (tức hợp đồng đã ký), kể cả deal đã hoàn thành.
    signed_deals: int = 0
    # Giá trị trung bình mỗi deal đã chốt = tiền các mốc của deal CÒN HIỆU LỰC ÷ số deal đó. Deal
    # không thành công không tham gia (khoản cọc lẻ của deal đổ vỡ sẽ kéo trung bình xuống vô lý).
    average_deal_value: Decimal = Decimal(0)


def totals(rows: list[MilestoneMoney]) -> MoneyTotals:
    collected = sum((r.amount for r in rows if r.collected), Decimal(0))
    outstanding = sum((r.amount for r in rows if not r.collected), Decimal(0))
    live = [r for r in rows if not r.lost]
    live_deals = {r.deal_id for r in live if r.deal_id is not None}
    average = (
        (sum((r.amount for r in live), Decimal(0)) / len(live_deals)).quantize(Decimal("0.01"))
        if live_deals
        else Decimal(0)
    )
    return MoneyTotals(
        contracted=collected + outstanding,
        collected=collected,
        outstanding=outstanding,
        milestones_pending=sum(1 for r in rows if not r.collected),
        signed_deals=len({r.deal_id for r in rows if r.deal_id is not None}),
        average_deal_value=average,
    )
