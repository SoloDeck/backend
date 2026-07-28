"""Ảnh freelancer chèn vào thư nhắc.

Vì sao có: freelancer muốn gửi kèm mã QR chuyển khoản họ chụp sẵn từ app ngân hàng, ảnh
sản phẩm, ảnh mockup — những thứ hệ thống không tự dựng được.

CHỈ NHẬN ẢNH. Email không phát được video, và tệp .docx/.pdf đính kèm thì trình đọc mail
hiện thành cục tải về chứ không hiện trong thân thư — mà mục đích ở đây là để khách NHÌN
THẤY ngay (nhất là mã QR). Video muốn gửi thì dán link vào nội dung.

Ảnh nhúng bằng `cid:` chứ không phải `data:` — Gmail cắt bỏ ảnh `data:`.  #Huynh
"""

from dataclasses import dataclass
from html import escape
from typing import Any

import structlog

from src.infrastructure.storage.object_storage import MAX_FILE_SIZE_BYTES, ObjectStorage
from src.shared.exceptions.domain import BusinessRuleError, ValidationError

log = structlog.get_logger(__name__)

# Chỉ ảnh — xem docstring module.
ALLOWED_IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})

# Trần số ảnh cho một thư. Thư 10 ảnh thì hộp thư khách nặng và nhiều nơi chặn thẳng.
MAX_IMAGES_PER_REMINDER = 5


@dataclass(frozen=True)
class ReminderImage:
    key: str
    filename: str
    content_type: str

    def as_dict(self) -> dict[str, str]:
        return {"key": self.key, "filename": self.filename, "content_type": self.content_type}


def validate_image(*, content_type: str, data: bytes) -> None:
    """Chặn trước khi tốn một vòng lên kho lưu trữ."""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise ValidationError(
            f"Chỉ nhận ảnh (PNG, JPEG, WebP, GIF). Định dạng '{content_type}' không dùng được. "
            "Video thì bạn dán link vào nội dung thư giúp nhé."
        )
    if len(data) > MAX_FILE_SIZE_BYTES:
        raise ValidationError(
            f"Ảnh quá lớn. Tối đa {MAX_FILE_SIZE_BYTES // 1024 // 1024} MB mỗi ảnh."
        )


def parse_attachments(raw: Any) -> list[ReminderImage]:
    """Đọc cột JSONB thành danh sách có kiểu. Bản ghi hỏng thì bỏ qua, không nổ."""
    out: list[ReminderImage] = []
    for item in raw or []:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        out.append(
            ReminderImage(
                key=str(item["key"]),
                filename=str(item.get("filename") or "image"),
                content_type=str(item.get("content_type") or "image/png"),
            )
        )
    return out


async def load_image_bytes(
    storage: ObjectStorage, images: list[ReminderImage]
) -> dict[str, bytes]:
    """Tải ảnh từ kho về, trả `{cid: bytes}`.

    Ảnh nào tải hỏng thì BỎ QUA chứ không làm hỏng cả lá thư — mất một tấm ảnh còn hơn
    freelancer không gửi được lời nhắc nào.  #Huynh
    """
    loaded: dict[str, bytes] = {}
    for index, image in enumerate(images):
        try:
            data, _ = await storage.download(image.key)
        except Exception as exc:  # noqa: BLE001
            log.warning("reminder.image_load_failed", key=image.key, error=str(exc))
            continue
        loaded[f"img{index}"] = data
    return loaded


def images_html(images: list[ReminderImage], srcs: dict[str, str]) -> str:
    """Khối ảnh chèn cuối thư. `srcs` là `{cid: đường dẫn}` (cid:... hoặc data:...)."""
    if not srcs:
        return ""
    blocks = []
    for index, image in enumerate(images):
        src = srcs.get(f"img{index}")
        if not src:
            continue
        blocks.append(
            f'<div style="margin:12px 0"><img src="{escape(src, quote=True)}" '
            f'alt="{escape(image.filename)}" '
            'style="max-width:100%;height:auto;border-radius:8px;border:1px solid #E5E7EB"></div>'
        )
    return "".join(blocks)


def ensure_within_limit(current: int) -> None:
    if current >= MAX_IMAGES_PER_REMINDER:
        raise BusinessRuleError(f"Mỗi lời nhắc chỉ đính kèm tối đa {MAX_IMAGES_PER_REMINDER} ảnh.")
