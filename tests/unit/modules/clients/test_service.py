"""Xoá khách: vì sao bị chặn thì phải nói được ra.

Người dùng tạo khách thử + dự án thử, xoá dự án, rồi xoá khách -> vẫn bị chặn. Đó là
CỐ Ý (163fb7f: bản ghi đã xoá mềm vẫn là lịch sử giao dịch), nhưng trước đây câu báo lỗi
lại nói "client that has existing deals" — người dùng nhìn màn hình trống trơn, không
hiểu còn vướng gì, cũng không còn gì để xoá tiếp.
"""

import uuid
from unittest.mock import AsyncMock

import pytest

from src.modules.clients.application.service import ClientsService
from src.modules.clients.infrastructure.repository import ClientsRepository
from src.shared.exceptions.domain import BusinessRuleError


def _service(counts: dict[str, int]) -> tuple[ClientsService, object]:
    client = type("ClientStub", (), {"deleted_at": None})()
    repo = AsyncMock()
    repo.get_by_id.return_value = client
    repo.count_transactions.return_value = counts
    return ClientsService(db=AsyncMock(), repo=repo), client


async def test_bao_loi_goi_ten_thu_dang_vuong() -> None:
    """Câu chặn phải nói rõ còn mấy dự án / hoá đơn / hợp đồng, bằng tiếng Việt."""
    service, _ = _service({"deals": 2, "invoices": 1, "contracts": 0})

    with pytest.raises(BusinessRuleError) as exc:
        await service.delete(uuid.uuid4(), uuid.uuid4())

    message = str(exc.value)
    assert "2 dự án" in message
    assert "1 hóa đơn" in message
    assert "hợp đồng" not in message.split("nên chưa xóa được")[0]


async def test_bao_loi_noi_ro_ban_da_xoa_van_tinh() -> None:
    """Chỗ người dùng bế tắc: dự án đã xoá rồi mà vẫn chặn -> phải nói ra, kèm lối đi khác."""
    service, _ = _service({"deals": 1, "invoices": 0, "contracts": 0})

    with pytest.raises(BusinessRuleError) as exc:
        await service.delete(uuid.uuid4(), uuid.uuid4())

    message = str(exc.value)
    assert "đã xóa vẫn tính" in message
    assert "Lưu trữ" in message


async def test_khong_vuong_gi_thi_xoa_duoc() -> None:
    service, client = _service({"deals": 0, "invoices": 0, "contracts": 0})

    await service.delete(uuid.uuid4(), uuid.uuid4())

    assert client.deleted_at is not None


async def test_dem_giao_dich_van_tinh_ca_ban_da_xoa_mem() -> None:
    """Khoá lại luật cố ý: `count_transactions` KHÔNG lọc `deleted_at`.

    Đây là quy tắc nghiệp vụ đã chốt, không phải sơ suất — hoá đơn và hợp đồng là chứng từ,
    xoá khách đi thì chúng mất chỗ bám. Ai định "sửa" bằng cách thêm bộ lọc soft-delete sẽ
    làm đỏ test này trước khi kịp làm đỏ bộ integration.
    """
    captured = []

    db = AsyncMock()

    async def _scalar(stmt):
        captured.append(str(stmt.compile(compile_kwargs={"literal_binds": False})))
        return 0

    db.scalar.side_effect = _scalar

    counts = await ClientsRepository(db).count_transactions(uuid.uuid4())

    assert set(counts) == {"deals", "invoices", "contracts"}
    assert len(captured) == 3
    assert all("deleted_at" not in sql for sql in captured), captured
