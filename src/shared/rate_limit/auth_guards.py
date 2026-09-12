"""Chốt chặn nhịp gọi cho các cửa xác thực.

Vì sao phải có riêng file này thay vì để trống như trước: ba cửa `/auth/login`,
`/auth/password-reset/request` và `/auth/password-reset/confirm` đều KHÔNG cần đăng nhập,
và cả ba đều nhận số lần gọi không giới hạn. Hậu quả đã cân nhắc, theo thứ tự nặng dần:

1. **Dò mật khẩu không giới hạn.** Biết email là bắn được bao nhiêu lần tuỳ thích, không
   có khoá tài khoản, không có độ trễ tăng dần.
2. **Sập dịch vụ rất rẻ.** Mỗi lần đăng nhập với email CÓ THẬT chạy một lượt Argon2id
   m=65536 — tức 64 MiB RAM và khoảng 70 ms CPU cho MỖI request. Vài chục request đồng
   thời là hết RAM và hết CPU, người dùng thật thấy app treo.
3. **Dội bom email và cháy hạn mức gửi.** `/password-reset/request` gửi thư ngay trong
   request. Bắn hàng nghìn lượt vừa nhét đầy hộp thư nạn nhân, vừa đốt sạch hạn mức gửi
   trong ngày của hộp thư hệ thống — và khi hạn mức cháy thì CẢ HỆ THỐNG mất email tới
   hôm sau: không ai nhận được OTP, không gửi được hoá đơn, không gửi được nhắc hẹn.

Giới hạn ở đây là **theo tiến trình**, giống `FixedWindowRateLimiter` vốn có. Chạy nhiều
worker thì trần thực tế nhân lên theo số worker. Vẫn đáng làm — nó cắt đứt kiểu tấn công
một máy bắn liên tục, là kiểu thực tế nhất ở quy mô sản phẩm này — nhưng muốn trần cứng
toàn cụm thì phải đếm bằng Redis (đã có sẵn `settings.redis_url`). Ghi rõ ở đây để người
sau không tưởng nhầm là đã kín.  #Huynh
"""

from fastapi import Request

from src.shared.rate_limit.limiter import FixedWindowRateLimiter

# Đăng nhập: rộng tay với người gõ nhầm mật khẩu vài lần, nhưng cắt được máy dò.
_login_theo_ip = FixedWindowRateLimiter(
    max_requests=30,
    window_seconds=300,
    thong_bao="Có quá nhiều lượt đăng nhập từ máy của bạn. Chờ khoảng 5 phút rồi thử lại nhé.",
)
_login_theo_email = FixedWindowRateLimiter(
    max_requests=10,
    window_seconds=300,
    thong_bao=(
        "Tài khoản này vừa bị thử đăng nhập nhiều lần. Chờ khoảng 5 phút rồi thử lại, "
        "hoặc dùng chức năng quên mật khẩu."
    ),
)

# Xin mã OTP: chặt nhất, vì mỗi lượt là một lá thư thật rời hệ thống.
_xin_ma_theo_email = FixedWindowRateLimiter(
    max_requests=3,
    window_seconds=900,
    thong_bao=(
        "Mã OTP đã được gửi rồi. Kiểm tra hộp thư (kể cả mục spam) giúp mình, "
        "sau 15 phút mới xin được mã mới."
    ),
)
_xin_ma_theo_ip = FixedWindowRateLimiter(
    max_requests=10,
    window_seconds=3600,
    thong_bao="Máy của bạn đã xin mã quá nhiều lần trong một giờ. Thử lại sau nhé.",
)

# Gõ mã OTP: lớp thứ hai sau bộ đếm `attempts` trên chính bản ghi mã.
_go_ma_theo_ip = FixedWindowRateLimiter(
    max_requests=10,
    window_seconds=900,
    thong_bao="Bạn đã nhập sai mã quá nhiều lần. Chờ 15 phút rồi xin mã mới giúp mình nhé.",
)


def dia_chi_goi_den(request: Request) -> str:
    """Địa chỉ IP của người gọi, có tính tới lớp proxy đứng trước.

    Deploy thật có nginx đứng trước nên `request.client.host` luôn là địa chỉ nội bộ của
    proxy — đếm theo nó thì cả thế giới chung một rổ, chốt chặn thành ra chặn nhầm người
    dùng thật. Lấy nhịp đầu tiên của `X-Forwarded-For` (proxy gần người dùng nhất ghi vào
    đó). Header này người gọi giả được, nhưng giả được cũng chỉ tự chia nhỏ rổ của chính
    mình chứ không vượt được trần theo email ở trên.  #Huynh
    """
    chuyen_tiep = request.headers.get("x-forwarded-for")
    if chuyen_tiep:
        dau = chuyen_tiep.split(",")[0].strip()
        if dau:
            return dau
    return request.client.host if request.client else "khong-ro"


def chan_nhip_dang_nhap(request: Request, email: str) -> None:
    _login_theo_ip.check(f"ip:{dia_chi_goi_den(request)}")
    _login_theo_email.check(f"email:{email.lower()}")


def chan_nhip_xin_ma(request: Request, email: str) -> None:
    _xin_ma_theo_ip.check(f"ip:{dia_chi_goi_den(request)}")
    _xin_ma_theo_email.check(f"email:{email.lower()}")


def chan_nhip_go_ma(request: Request) -> None:
    _go_ma_theo_ip.check(f"ip:{dia_chi_goi_den(request)}")


def reset_moi_bo_dem() -> None:
    """Xoá sạch bộ đếm — chỉ dùng cho test, để các bài không ảnh hưởng lẫn nhau."""
    for bo_dem in (
        _login_theo_ip,
        _login_theo_email,
        _xin_ma_theo_email,
        _xin_ma_theo_ip,
        _go_ma_theo_ip,
    ):
        bo_dem.reset()
