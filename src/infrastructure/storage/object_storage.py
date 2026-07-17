"""Lưu file lên object storage S3-compatible (MinIO khi dev, S3/R2 khi deploy).

Vì sao có file này: frontend trước đây nhét **cả nội dung file dạng base64 vào
localStorage**. Ba vấn đề:

1. localStorage chỉ ~5MB — một cái PDF là vỡ.
2. Đổi máy là mất sạch.
3. File không bao giờ rời khỏi trình duyệt, nên không gửi được cho khách.

``.env.example`` vốn đã khai ``STORAGE_ENDPOINT / STORAGE_BUCKET / STORAGE_ACCESS_KEY``
— team định dùng S3 từ đầu, chỉ chưa ai dựng. Giờ dựng, và **không đụng gì tới code khi
deploy**: chỉ đổi ``STORAGE_ENDPOINT`` sang AWS S3 hoặc Cloudflare R2.  #Huynh
"""

import uuid
from dataclasses import dataclass
from typing import Any

import boto3
import structlog
from botocore.config import Config
from botocore.exceptions import ClientError

from src.config.settings import settings

log = structlog.get_logger(__name__)

# Chỉ cho phép mấy loại file freelancer thật sự cần đính vào deal: hợp đồng scan, biên
# nhận chuyển khoản, ảnh chụp bàn giao. KHÔNG mở cửa cho mọi thứ — nhận .exe, .html là
# mời tai nạn (XSS khi mở file, phát tán mã độc).  #Huynh
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/webp",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
    }
)

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

# Suy ra MIME từ đuôi file khi trình duyệt không nói.
#
# Trên Windows, trình duyệt đôi khi trả về content_type RỖNG cho đúng một file PDF (thiếu
# ánh xạ MIME trong registry). Chặn theo content_type khi đó là người dùng chọn PDF thật
# mà bị từ chối, không hiểu vì sao.  #Huynh
EXTENSION_TO_CONTENT_TYPE: dict[str, str] = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def resolve_content_type(content_type: str | None, filename: str) -> str:
    """Lấy MIME đáng tin: ưu tiên trình duyệt, thiếu thì suy từ đuôi file."""
    if content_type and content_type in ALLOWED_CONTENT_TYPES:
        return content_type

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return EXTENSION_TO_CONTENT_TYPE.get(ext, content_type or "application/octet-stream")


@dataclass
class ObjectStorage:
    """Bọc S3. Dùng chung cho file đính kèm deal, và sau này cho avatar."""

    _client: Any = None

    @property
    def enabled(self) -> bool:
        return bool(settings.storage_endpoint and settings.storage_access_key)

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=settings.storage_endpoint,
                aws_access_key_id=settings.storage_access_key,
                aws_secret_access_key=settings.storage_secret_key,
                region_name=settings.storage_region or "us-east-1",
                # path-style: MinIO không hỗ trợ virtual-host style như AWS.
                config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
            )
        return self._client

    def ensure_bucket(self) -> None:
        """Tạo bucket nếu chưa có. Gọi lúc app khởi động."""
        if not self.enabled:
            log.warning("storage.disabled", reason="STORAGE_ENDPOINT hoặc ACCESS_KEY rỗng")
            return

        bucket = settings.storage_bucket
        try:
            self.client.head_bucket(Bucket=bucket)
        except ClientError:
            self.client.create_bucket(Bucket=bucket)
            log.info("storage.bucket_created", bucket=bucket)

    def upload(self, *, data: bytes, content_type: str, prefix: str, filename: str) -> str:
        """Đẩy file lên, trả về ``storage_key`` để lưu vào DB.

        Key có UUID nên **không đè nhau** dù hai người upload cùng tên file, và không đoán
        được từ bên ngoài. Tên gốc lưu riêng trong DB để hiển thị lại cho người dùng.
        """
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
        key = f"{prefix}/{uuid.uuid4()}.{ext}"

        self.client.put_object(
            Bucket=settings.storage_bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return key

    def download(self, key: str) -> tuple[bytes, str]:
        """Tải file về (bytes, content_type)."""
        obj = self.client.get_object(Bucket=settings.storage_bucket, Key=key)
        return obj["Body"].read(), obj.get("ContentType", "application/octet-stream")

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=settings.storage_bucket, Key=key)


object_storage = ObjectStorage()
