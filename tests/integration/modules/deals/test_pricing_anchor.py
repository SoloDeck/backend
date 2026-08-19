"""Mốc neo giá — `DealsRepository.comparable_deal_values`.

Hàm này lấy giá THẬT của các dự án đã chốt xong để làm mốc cho báo giá kế tiếp. Nó là nền của
cả hệ định giá: sai ở đây thì giá gợi ý sai, mà sai kiểu im lặng — không lỗi, không cảnh báo,
chỉ là con số khác.

Hai bài đầu khoá hai lỗi ngầm vừa sửa; bài cuối khoá lời hứa "lưu kho không đụng tới giá".
#Huynh
"""

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import update

from src.infrastructure.database.models import DealModel
from src.modules.deals.infrastructure.repository import DealsRepository
from tests.integration.modules.deals.test_deals_api import _auth, _create_deal


async def _won(db_session, deal_id: str, value: int, days_ago: int) -> None:
    """Đánh dấu deal đã chốt xong với giá thật và ngày đóng lùi lại."""
    await db_session.execute(
        update(DealModel)
        .where(DealModel.id == uuid.UUID(deal_id))
        .values(
            stage="completed_and_billed",
            actual_value=value,
            closed_at=datetime.now(UTC) - timedelta(days=days_ago),
        )
    )
    await db_session.commit()


async def _owner_id(client: AsyncClient, headers: dict) -> uuid.UUID:
    me = await client.get("/api/v1/users/me", headers=headers)
    return uuid.UUID(me.json()["data"]["id"])


class TestMocNeoGia:
    async def test_bo_qua_du_an_da_loai_bo(self, client: AsyncClient, db_session) -> None:
        """Dự án freelancer đã loại bỏ thì cũng ra khỏi lịch sử giá.

        Bản trước thiếu `deleted_at IS NULL` — neo giá vào những deal mà chính chủ coi như
        không tồn tại.
        """
        headers = await _auth(client)
        giu = await _create_deal(client, headers, "Còn giữ")
        bo = await _create_deal(client, headers, "Đã loại bỏ")
        await _won(db_session, giu["id"], 50_000_000, days_ago=10)
        await _won(db_session, bo["id"], 900_000_000, days_ago=5)

        resp = await client.delete(f"/api/v1/deals/{bo['id']}", headers=headers)
        assert resp.status_code in (200, 204), resp.text

        _, moi_nhom = await DealsRepository(db=db_session).comparable_deal_values(
            await _owner_id(client, headers), None
        )
        assert [int(v) for v in moi_nhom] == [50_000_000]

    async def test_sap_theo_ngay_chot_deal_khong_theo_lan_cham_cuoi(
        self, client: AsyncClient, db_session
    ) -> None:
        """CÁI BẪY: `updated_at` có `onupdate` + trigger PG.

        Bản trước sắp theo `updated_at`, nên chỉ cần sửa một chữ trong một dự án cũ là bộ mười
        mốc neo giá xáo lại, và giá gợi ý cho báo giá kế tiếp đổi mà không ai chạm vào giá.
        """
        headers = await _auth(client)
        cu = await _create_deal(client, headers, "Chốt lâu rồi")
        moi = await _create_deal(client, headers, "Vừa chốt")
        await _won(db_session, cu["id"], 10_000_000, days_ago=300)
        await _won(db_session, moi["id"], 20_000_000, days_ago=5)

        repo = DealsRepository(db=db_session)
        owner = await _owner_id(client, headers)
        truoc = [int(v) for v in (await repo.comparable_deal_values(owner, None))[1]]
        assert truoc == [20_000_000, 10_000_000]

        # Chạm vào dự án CŨ — chỉ đổi tên, không đụng gì tới tiền.
        resp = await client.patch(
            f"/api/v1/deals/{cu['id']}",
            json={"client_id": cu["client_id"], "title": "Chốt lâu rồi (đổi tên)"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        db_session.expire_all()

        sau = [int(v) for v in (await repo.comparable_deal_values(owner, None))[1]]
        assert sau == truoc, "Đổi tên một dự án cũ KHÔNG được làm xáo mốc neo giá"

    async def test_du_an_da_luu_kho_van_lam_moc_neo_gia(
        self, client: AsyncClient, db_session
    ) -> None:
        """Lưu kho chỉ giấu khỏi bảng Kanban, tuyệt đối không đụng tới định giá.

        Lọc bỏ kho ở đây là freelancer càng lâu năm càng mất mốc giá — đúng ngược ý đồ của
        việc giữ lại dự án cũ.
        """
        headers = await _auth(client)
        rat_cu = await _create_deal(client, headers, "Chốt 400 ngày trước")
        await _won(db_session, rat_cu["id"], 77_000_000, days_ago=400)

        # Đã ra khỏi bảng...
        tren_bang = await client.get("/api/v1/deals?archived=false", headers=headers)
        assert tren_bang.json()["data"] == []

        # ...nhưng vẫn là mốc giá.
        _, moi_nhom = await DealsRepository(db=db_session).comparable_deal_values(
            await _owner_id(client, headers), None
        )
        assert [int(v) for v in moi_nhom] == [77_000_000]
