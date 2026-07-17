"""Bóc chữ từ file khách gửi, để AI đọc mà chấm điểm deal.

Đây là mảnh còn thiếu quan trọng nhất của hệ thống chấm điểm.

Trước đây: deal tạo tay **luôn mất trọn 25 điểm ngân sách** vì luật chấm điểm chỉ tính
những gì KHÁCH nói — mà khách thì "chưa nói gì" (ô "Giá trị dự kiến" là freelancer tự
nhập). Nên deal tự tạo gần như luôn ra COLD.

Nhưng nếu khách **gửi hẳn một file brief PDF** thì **ĐÓ CHÍNH LÀ LỜI KHÁCH**. Bóc chữ ra,
đưa vào khối "KHÁCH HÀNG NÓI GÌ" của prompt — AI đọc được yêu cầu thật, ngân sách thật,
deadline thật. Điểm số mới phản ánh đúng.  #Huynh
"""

import io

import structlog
from pypdf import PdfReader

log = structlog.get_logger(__name__)

# Cắt bớt chữ bóc ra trước khi đưa cho AI.
#
# Groq free tier giới hạn ~30.000 token/phút. Một file brief 40 trang có thể vượt xa mức
# đó, và nhồi cả cuốn sách vào prompt cũng không làm AI chấm chuẩn hơn — phần đầu tài
# liệu (mô tả yêu cầu, phạm vi, ngân sách) mới là thứ đáng đọc. 12.000 ký tự ≈ 3-4k token,
# đủ cho một brief dự án freelance bình thường.  #Huynh
MAX_TEXT_CHARS = 12_000


def extract_pdf_text(data: bytes) -> str | None:
    """Bóc chữ từ PDF. Trả về ``None`` nếu không bóc được.

    ``None`` là kết quả HỢP LỆ, không phải lỗi: PDF scan từ máy in là **ảnh**, không có
    lớp chữ nào để bóc. Muốn đọc được phải OCR — nằm ngoài phạm vi. Giao diện phải nói
    rõ để người dùng biết file đó AI không đọc được, thay vì im lặng rồi họ tưởng AI đã
    đọc.
    """
    try:
        reader = PdfReader(io.BytesIO(data))
        parts: list[str] = []

        for page in reader.pages:
            text = (page.extract_text() or "").strip()
            if text:
                parts.append(text)

            # Đủ chữ rồi thì dừng — không cần đọc hết 40 trang.
            if sum(len(p) for p in parts) >= MAX_TEXT_CHARS:
                break

        full = "\n\n".join(parts).strip()
        if not full:
            return None

        return full[:MAX_TEXT_CHARS]

    except Exception as exc:  # noqa: BLE001
        # PDF hỏng, mã hoá, hoặc định dạng lạ. Không được làm hỏng cả lần upload —
        # file vẫn lưu được, chỉ là AI không đọc được nội dung.
        log.warning("attachment.pdf_extract_failed", error=str(exc))
        return None
