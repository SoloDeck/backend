"""Dựng header `Content-Disposition` cho tệp tải về.

Vì sao cần cả một hàm cho một dòng header: header HTTP chỉ mang được ký tự latin-1. Tên
tệp người dùng đặt ở sản phẩm này gần như luôn có dấu tiếng Việt ("báo giá gửi khách.pdf"),
và nhét thẳng vào f-string thì Starlette ném `UnicodeEncodeError` lúc mã hoá header —
người dùng bấm tải về nhận đúng một lỗi 500 trống trơn, không hiểu vì sao.

Cách đúng theo RFC 6266: đưa HAI giá trị.
  * `filename=` — bản rút gọn chỉ còn ASCII, cho trình duyệt cũ.
  * `filename*=UTF-8''...` — bản mã hoá phần trăm, mọi trình duyệt hiện nay đều ưu tiên
    giá trị này, nên người dùng vẫn nhận đúng tên tiếng Việt có dấu.

Tiện thể chặn luôn một lỗ nhỏ: dấu nháy kép hoặc xuống dòng trong tên tệp cắt được header
làm đôi (tên tệp là chuỗi do người ngoài đặt khi họ tải tệp lên).  #Huynh
"""

import unicodedata
from urllib.parse import quote

TEN_MAC_DINH = "tai-ve"

# Ký tự cắt được header làm đôi hoặc làm hỏng cú pháp `filename="..."`.
KY_TU_CAM = frozenset(['"', "\\", "/", "\r", "\n"])


def _rut_ve_ascii(ten: str) -> str:
    """Bỏ dấu tiếng Việt để còn một cái tên đọc được bằng ASCII thuần."""
    # NFKD tách chữ khỏi dấu, rồi bỏ phần dấu: "báo giá" -> "bao gia".
    khong_dau = unicodedata.normalize("NFKD", ten).encode("ascii", "ignore").decode("ascii")
    sach = "".join(c if c.isprintable() and c not in KY_TU_CAM else "_" for c in khong_dau)
    return sach.strip() or TEN_MAC_DINH


def content_disposition_dinh_kem(ten_tep: str | None) -> str:
    """Giá trị header cho một tệp tải về, an toàn với tên tiếng Việt."""
    ten = (ten_tep or "").strip() or TEN_MAC_DINH
    ascii_thuan = _rut_ve_ascii(ten)
    # `quote` với safe rỗng để dấu cách thành %20 chứ không thành dấu cộng.
    ma_hoa = quote(ten, safe="")
    return f"attachment; filename=\"{ascii_thuan}\"; filename*=UTF-8''{ma_hoa}"
