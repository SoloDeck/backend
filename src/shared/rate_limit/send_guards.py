"""Chốt chặn nhịp GỬI giấy tờ cho khách (báo giá, hợp đồng).

Mỗi lượt gửi là một lá thư THẬT rời hệ thống, và mọi thư của mọi người dùng đều đi qua MỘT hộp
thư hệ thống dùng chung hạn mức gửi trong ngày của Gmail. Một tài khoản bấm gửi dồn dập (hoặc bị
script bắn vào endpoint) đốt hết hạn mức đó thì CẢ HỆ THỐNG mất email tới hôm sau: không ai nhận
được OTP, hoá đơn hay lời nhắc thanh toán — cùng kiểu hậu quả đã nêu ở `auth_guards`.

Trần ở đây rộng tay với người dùng thật (20 lượt trong 10 phút là hơn hẳn nhu cầu của một
freelancer) và chỉ cắt kiểu bấm/bắn liên tục. Giới hạn **theo tiến trình**, giống
`FixedWindowRateLimiter` vốn có: chạy nhiều worker thì trần thực tế nhân lên theo số worker.
#Huynh
"""

import uuid

from src.shared.rate_limit.limiter import FixedWindowRateLimiter

_gui_giay_to_theo_nguoi_dung = FixedWindowRateLimiter(
    max_requests=20,
    window_seconds=600,
    thong_bao=(
        "Bạn vừa gửi khá nhiều giấy tờ trong thời gian ngắn. "
        "Chờ vài phút rồi gửi tiếp giúp mình nhé."
    ),
)


def chan_nhip_gui_giay_to(user_id: uuid.UUID) -> None:
    """Ghi một lượt gửi của `user_id`; quá trần thì ném `RateLimitError` (HTTP 429)."""
    _gui_giay_to_theo_nguoi_dung.check(f"user:{user_id}")


def reset_bo_dem() -> None:
    """Xoá sạch bộ đếm — chỉ dùng cho test."""
    _gui_giay_to_theo_nguoi_dung.reset()
