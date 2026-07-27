"""Test cho tính năng đính kèm file — TRƯỚC ĐÂY KHÔNG CÓ CÁI NÀO.

Lý do không có: `DealAttachmentService` gọi thẳng singleton `object_storage`, nên muốn
test bất cứ thứ gì đụng tới file là phải có MinIO thật đang chạy. Không ai dựng MinIO
chỉ để chạy unit test, nên tính năng này đi thẳng lên sản phẩm mà chưa từng được kiểm.

Sau khi kho file được TIÊM VÀO, mấy test dưới chạy trong vài mili giây, không cần S3,
không cần Docker.  #Huynh
"""

import uuid

import pytest

from src.infrastructure.database.models import DealModel
from src.modules.deals.application.attachment_service import DealAttachmentService
from src.shared.exceptions.domain import NotFoundError, ValidationError


class _KhoFileGia:
    """Đứng thay ObjectStorage. Không đụng mạng, ghi lại đã được gọi những gì."""

    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.da_upload: list[dict] = []
        self.da_xoa: list[str] = []
        self.key_tra_ve = "deals/gia/abc.png"

    async def upload(self, *, data: bytes, content_type: str, prefix: str, filename: str) -> str:
        self.da_upload.append(
            {"data": data, "content_type": content_type, "prefix": prefix, "filename": filename}
        )
        return self.key_tra_ve

    async def download(self, key: str) -> tuple[bytes, str]:
        return b"noi dung", "image/png"

    async def delete(self, key: str) -> None:
        self.da_xoa.append(key)


class _DbGia:
    """Phiên DB giả: đủ dùng cho `scalar` + `add` + `flush` + `refresh`."""

    def __init__(self, tra_ve: object = None) -> None:
        self._tra_ve = tra_ve
        self.da_them: list[object] = []
        self.da_xoa: list[object] = []

    async def scalar(self, *_args: object, **_kw: object) -> object:
        return self._tra_ve

    def add(self, obj: object) -> None:
        self.da_them.append(obj)

    async def flush(self) -> None:
        return None

    async def refresh(self, obj: object) -> None:
        return None

    async def delete(self, obj: object) -> None:
        self.da_xoa.append(obj)


def _deal(owner_id: uuid.UUID) -> DealModel:
    return DealModel(id=uuid.uuid4(), owner_user_id=owner_id, title="Gym")


async def test_upload_dung_kho_file_duoc_tiem_vao() -> None:
    chu = uuid.uuid4()
    deal = _deal(chu)
    kho = _KhoFileGia()
    svc = DealAttachmentService(db=_DbGia(deal), storage=kho)  # type: ignore[arg-type]

    att = await svc.upload(
        user_id=chu,
        deal_id=deal.id,
        filename="brief.png",
        content_type="image/png",
        data=b"anh gia",
    )

    # Đi qua kho ĐƯỢC TIÊM, không phải singleton toàn cục.
    assert len(kho.da_upload) == 1
    assert kho.da_upload[0]["prefix"] == f"deals/{deal.id}"
    # storage_key lưu vào DB phải là key kho trả về, không phải tên file người dùng đặt.
    assert att.storage_key == kho.key_tra_ve
    assert att.size_bytes == len(b"anh gia")
    assert svc.db.da_them == [att]  # type: ignore[attr-defined]


async def test_upload_tu_choi_dinh_dang_la() -> None:
    chu = uuid.uuid4()
    deal = _deal(chu)
    kho = _KhoFileGia()
    svc = DealAttachmentService(db=_DbGia(deal), storage=kho)  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        await svc.upload(
            user_id=chu,
            deal_id=deal.id,
            filename="virus.exe",
            content_type="application/x-msdownload",
            data=b"MZ",
        )

    # Quan trọng: từ chối RỒI mới upload — không được đẩy file lạ lên rồi mới kiểm.
    assert kho.da_upload == []


async def test_deal_cua_nguoi_khac_thi_khong_upload_duoc() -> None:
    kho = _KhoFileGia()
    # DB không trả về deal nào -> coi như người này không sở hữu deal đó.
    svc = DealAttachmentService(db=_DbGia(None), storage=kho)  # type: ignore[arg-type]

    with pytest.raises(NotFoundError):
        await svc.upload(
            user_id=uuid.uuid4(),
            deal_id=uuid.uuid4(),
            filename="brief.png",
            content_type="image/png",
            data=b"x",
        )

    # Kiểm quyền phải chặn TRƯỚC khi file kịp chạm kho.
    assert kho.da_upload == []


async def test_content_type_rong_van_nhan_ra_pdf_tu_duoi_file() -> None:
    """Trình duyệt trên Windows đôi khi trả content_type RỖNG cho đúng một file PDF
    (thiếu ánh xạ MIME trong registry). Chặn theo content_type khi đó là từ chối một
    file PDF thật của khách.  #Huynh
    """
    chu = uuid.uuid4()
    deal = _deal(chu)
    kho = _KhoFileGia()
    svc = DealAttachmentService(db=_DbGia(deal), storage=kho)  # type: ignore[arg-type]

    att = await svc.upload(
        user_id=chu,
        deal_id=deal.id,
        filename="brief.pdf",
        content_type="",  # trình duyệt không nói gì
        data=b"%PDF-1.4 gia lap",
    )

    assert kho.da_upload[0]["content_type"] == "application/pdf"
    assert att.content_type == "application/pdf"
