"""Kho lưu trữ — dự án hoàn thành đã đóng quá 90 ngày.

Cột "Hoàn Thành" trên bảng Kanban giữ mọi dự án đã xong nên phình vô tận, nhưng không được
xoá: chính những dự án đó là hồ sơ khách cũ, là mốc neo giá cho báo giá sau, và là số liệu tỷ
lệ thắng.

Kho ở đây là thứ SUY RA từ ``closed_at``, KHÔNG phải một cột trạng thái — nên không có gì để
đồng bộ, không có `UPDATE` nào, và vì thế không thể làm xáo mốc neo giá. Xem
``ARCHIVE_AFTER_DAYS``.  #Huynh
"""

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import update

from src.infrastructure.database.models import DealModel
from tests.integration.modules.deals.test_deals_api import (
    _auth,
    _create_client,
    _create_deal,
)


async def _set_stage_closed(db_session, deal_id: str, stage: str, days_ago: int | None) -> None:
    """Đặt giai đoạn + ngày đóng cho một deal, ghi thẳng vào DB.

    Không đi qua API chuyển giai đoạn: đường đó đòi báo giá đã chấp nhận và hợp đồng đã ký,
    mà mấy bài ở đây kiểm BỘ LỌC KHO chứ không kiểm luật chuyển giai đoạn.
    """
    closed_at = None if days_ago is None else datetime.now(UTC) - timedelta(days=days_ago)
    await db_session.execute(
        update(DealModel)
        .where(DealModel.id == uuid.UUID(deal_id))
        .values(stage=stage, closed_at=closed_at)
    )
    await db_session.commit()


def _titles(resp) -> list[str]:
    return [d["title"] for d in resp.json()["data"]]


class TestBoLocKho:
    async def test_bo_trong_thi_tra_het(self, client: AsyncClient, db_session) -> None:
        # Mặc định phải trả HẾT, cố ý: đây là đường DUY NHẤT lấy dự án của một khách
        # (`?client_id=`), nên lọc bỏ kho theo mặc định là hồ sơ khách mất sạch lịch sử.
        headers = await _auth(client)
        cu = await _create_deal(client, headers, "Dự án cũ")
        await _create_deal(client, headers, "Dự án mới")
        await _set_stage_closed(db_session, cu["id"], "completed_and_billed", 200)

        resp = await client.get("/api/v1/deals", headers=headers)
        assert set(_titles(resp)) == {"Dự án cũ", "Dự án mới"}

    async def test_archived_false_loai_du_an_cu_khoi_bang(
        self, client: AsyncClient, db_session
    ) -> None:
        headers = await _auth(client)
        cu = await _create_deal(client, headers, "Dự án cũ")
        await _create_deal(client, headers, "Dự án mới")
        await _set_stage_closed(db_session, cu["id"], "completed_and_billed", 200)

        resp = await client.get("/api/v1/deals?archived=false", headers=headers)
        assert _titles(resp) == ["Dự án mới"]

    async def test_archived_true_chi_tra_du_an_trong_kho(
        self, client: AsyncClient, db_session
    ) -> None:
        headers = await _auth(client)
        cu = await _create_deal(client, headers, "Dự án cũ")
        await _create_deal(client, headers, "Dự án mới")
        await _set_stage_closed(db_session, cu["id"], "completed_and_billed", 200)

        resp = await client.get("/api/v1/deals?archived=true", headers=headers)
        assert _titles(resp) == ["Dự án cũ"]

    async def test_ranh_gioi_dung_90_ngay(self, client: AsyncClient, db_session) -> None:
        # Chốt ranh giới bằng test để ai đổi con số cũng thấy ngay mình đang đổi cái gì.
        headers = await _auth(client)
        gan = await _create_deal(client, headers, "Đóng 89 ngày trước")
        xa = await _create_deal(client, headers, "Đóng 91 ngày trước")
        await _set_stage_closed(db_session, gan["id"], "completed_and_billed", 89)
        await _set_stage_closed(db_session, xa["id"], "completed_and_billed", 91)

        tren_bang = await client.get("/api/v1/deals?archived=false", headers=headers)
        assert _titles(tren_bang) == ["Đóng 89 ngày trước"]

        trong_kho = await client.get("/api/v1/deals?archived=true", headers=headers)
        assert _titles(trong_kho) == ["Đóng 91 ngày trước"]

    async def test_hoan_thanh_ma_khong_co_ngay_dong_thi_van_o_tren_bang(
        self, client: AsyncClient, db_session
    ) -> None:
        """Deal cũ sinh trước khi có ``closed_at`` KHÔNG được biến mất.

        ``NULL < <ngày>`` trong SQL cho ra NULL chứ không phải TRUE, nên viết ẩu là chúng rơi
        ra khỏi CẢ hai nhánh: không nằm trên bảng, cũng không nằm trong kho.
        """
        headers = await _auth(client)
        deal = await _create_deal(client, headers, "Deal cũ không có ngày đóng")
        await _set_stage_closed(db_session, deal["id"], "completed_and_billed", None)

        tren_bang = await client.get("/api/v1/deals?archived=false", headers=headers)
        assert _titles(tren_bang) == ["Deal cũ không có ngày đóng"]

        trong_kho = await client.get("/api/v1/deals?archived=true", headers=headers)
        assert trong_kho.json()["data"] == []

    async def test_deal_dang_chay_khong_bao_gio_vao_kho(
        self, client: AsyncClient, db_session
    ) -> None:
        # Kho chỉ tính `completed_and_billed`. Việc chưa xong thì dù cũ tới đâu cũng phải
        # nằm trên bảng.
        headers = await _auth(client)
        deal = await _create_deal(client, headers, "Đang chạy từ lâu", stage="qualified")
        await _set_stage_closed(db_session, deal["id"], "qualified", 999)

        trong_kho = await client.get("/api/v1/deals?archived=true", headers=headers)
        assert trong_kho.json()["data"] == []

    async def test_lost_chua_thuoc_pham_vi_dot_nay(
        self, client: AsyncClient, db_session
    ) -> None:
        # "Không chốt được" cũng phình y hệt nhưng đợt này cố ý chưa đụng tới. Khoá lại để
        # nếu sau này mở rộng thì thấy ngay bài này phải sửa.
        headers = await _auth(client)
        deal = await _create_deal(client, headers, "Deal không chốt được")
        await _set_stage_closed(db_session, deal["id"], "lost", 400)

        trong_kho = await client.get("/api/v1/deals?archived=true", headers=headers)
        assert trong_kho.json()["data"] == []

    async def test_kho_khong_lot_sang_nguoi_khac(
        self, client: AsyncClient, db_session
    ) -> None:
        headers_a = await _auth(client)
        cua_a = await _create_deal(client, headers_a, "Dự án của A")
        await _set_stage_closed(db_session, cua_a["id"], "completed_and_billed", 200)

        headers_b = await _auth(client)
        resp = await client.get("/api/v1/deals?archived=true", headers=headers_b)
        assert resp.json()["data"] == []

    async def test_ho_so_khach_hang_van_thay_du_an_da_luu_kho(
        self, client: AsyncClient, db_session
    ) -> None:
        """Chỗ dễ vỡ nhất — chống hồi quy.

        Freelancer giữ dự án cũ CHÍNH LÀ để nhớ khách. Nếu đường ``?client_id=`` lỡ lọc bỏ kho
        thì mở khách cũ ra là trắng trơn, mất đúng thứ cần nhất.
        """
        headers = await _auth(client)
        client_id = await _create_client(client, headers, "Khách quen")
        cu = await _create_deal(client, headers, "Dự án cũ", client_id=client_id)
        await _set_stage_closed(db_session, cu["id"], "completed_and_billed", 400)

        resp = await client.get(f"/api/v1/deals?client_id={client_id}", headers=headers)
        assert _titles(resp) == ["Dự án cũ"]

    async def test_kho_sap_theo_ngay_dong_moi_nhat_truoc(
        self, client: AsyncClient, db_session
    ) -> None:
        headers = await _auth(client)
        cu_hon = await _create_deal(client, headers, "Đóng 300 ngày trước")
        moi_hon = await _create_deal(client, headers, "Đóng 100 ngày trước")
        await _set_stage_closed(db_session, cu_hon["id"], "completed_and_billed", 300)
        await _set_stage_closed(db_session, moi_hon["id"], "completed_and_billed", 100)

        resp = await client.get(
            "/api/v1/deals?archived=true&sort_by=closed_at", headers=headers
        )
        assert _titles(resp) == ["Đóng 100 ngày trước", "Đóng 300 ngày trước"]
