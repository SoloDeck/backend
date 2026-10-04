"""Lưu trữ khách hàng: các dự án ĐANG CHẠY của khách tự vào Kho lưu trữ (Không thành công).

Freelancer bấm "Lưu trữ" khách là không còn theo khách đó nữa, nên dự án dở dang của họ không thể
cứ nằm trên bảng Kanban và trong "Còn phải thu". Chúng đi qua đúng đường chuyển giai đoạn sang
`lost` (có nhật ký, ngày đóng, huỷ lời nhắc) với lý do cố định. Dự án ĐÃ hoàn thành thì giữ
nguyên — đó là thương vụ thắng, không thể biến thành thất bại.
"""

from httpx import AsyncClient

from tests.integration.modules.deals.test_deals_api import _auth, _create_client, _create_deal
from tests.integration.modules.deals.test_deals_archive import _set_stage_closed
from tests.integration.modules.tasks.test_payment_task_invoice import _seed

LY_DO = "Khách hàng bị hạn chế"


async def _patch_khach(client: AsyncClient, headers: dict, client_id: str, **body):
    """PATCH khách và đòi 200: việc lưu trữ mà hỏng giữa chừng thì mọi khẳng định sau đó vô nghĩa.

    (Phiên DB của bài kiểm không tự hoàn tác khi request lỗi, nên deal đã kịp đóng trước chỗ lỗi
    vẫn nằm lại và che mất lỗi — không đòi 200 thì có đột biến lọt lưới.)
    """
    resp = await client.patch(f"/api/v1/clients/{client_id}", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp


async def _deal(client: AsyncClient, headers: dict, deal_id: str) -> dict:
    resp = await client.get(f"/api/v1/deals/{deal_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


class TestLuuTruKhachDuaDuAnVaoKho:
    async def test_du_an_dang_chay_chuyen_sang_khong_thanh_cong_kem_ly_do_co_dinh(
        self, client: AsyncClient
    ) -> None:
        headers = await _auth(client)
        khach = await _create_client(client, headers, "Khách A")
        moi = await _create_deal(client, headers, "Lead mới", client_id=khach)
        dam_phan = await _create_deal(
            client, headers, "Đang đàm phán", stage="in_negotiation", client_id=khach
        )

        resp = await _patch_khach(client, headers, khach, status="archived")

        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "archived"
        for ban_dau in (moi, dam_phan):
            deal = await _deal(client, headers, ban_dau["id"])
            assert deal["stage"] == "lost", ban_dau["title"]
            assert deal["lost_reason"] == LY_DO
            assert deal["closed_at"] is not None

    async def test_hien_trong_muc_khong_thanh_cong_cua_kho(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        khach = await _create_client(client, headers)
        a = await _create_deal(client, headers, "A", client_id=khach)
        b = await _create_deal(client, headers, "B", stage="qualified", client_id=khach)

        await _patch_khach(client, headers, khach, status="archived")

        resp = await client.get(
            "/api/v1/deals", params={"stage": "lost", "sort_by": "closed_at"}, headers=headers
        )
        rows = resp.json()["data"]
        assert {r["id"] for r in rows} == {a["id"], b["id"]}
        assert {r["lost_reason"] for r in rows} == {LY_DO}

    async def test_ly_do_nam_trong_nhat_ky_cua_deal(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        khach = await _create_client(client, headers)
        deal = await _create_deal(client, headers, "Có nhật ký", client_id=khach)

        await _patch_khach(client, headers, khach, status="archived")

        entries = (
            await client.get(f"/api/v1/deals/{deal['id']}/activity", headers=headers)
        ).json()["data"]
        loi = [e for e in entries if e["new_stage"] == "lost"]
        assert len(loi) == 1
        assert LY_DO in loi[0]["description"]

    async def test_deal_da_hoan_thanh_giu_nguyen(self, client: AsyncClient, db_session) -> None:
        headers = await _auth(client)
        khach = await _create_client(client, headers)
        xong = await _create_deal(client, headers, "Đã xong", client_id=khach)
        dang_chay = await _create_deal(client, headers, "Đang chạy", client_id=khach)
        await _set_stage_closed(db_session, xong["id"], "completed_and_billed", 5)

        await _patch_khach(client, headers, khach, status="archived")

        assert (await _deal(client, headers, xong["id"]))["stage"] == "completed_and_billed"
        assert (await _deal(client, headers, xong["id"]))["lost_reason"] is None
        assert (await _deal(client, headers, dang_chay["id"]))["stage"] == "lost"

    async def test_deal_da_mat_tu_truoc_giu_nguyen_ly_do_cu(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        khach = await _create_client(client, headers)
        deal = await _create_deal(client, headers, "Đã mất", client_id=khach)
        await client.post(
            f"/api/v1/deals/{deal['id']}/stage",
            json={"target_stage": "lost", "reason": "Khách chọn bên khác"},
            headers=headers,
        )

        await _patch_khach(client, headers, khach, status="archived")

        assert (await _deal(client, headers, deal["id"]))["lost_reason"] == "Khách chọn bên khác"

    async def test_khong_dung_den_deal_cua_khach_khac(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        bi_luu_tru = await _create_client(client, headers, "Khách bị lưu trữ")
        con_lai = await _create_client(client, headers, "Khách còn lại")
        deal_khac = await _create_deal(client, headers, "Của khách khác", client_id=con_lai)
        await _create_deal(client, headers, "Của khách bị lưu trữ", client_id=bi_luu_tru)

        await _patch_khach(client, headers, bi_luu_tru, status="archived")

        assert (await _deal(client, headers, deal_khac["id"]))["stage"] == "new_lead"


class TestChiChayDungLucChuyenSangLuuTru:
    async def test_doi_trang_thai_khac_khong_dong_deal(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        khach = await _create_client(client, headers)
        deal = await _create_deal(client, headers, "Vẫn chạy", client_id=khach)

        await _patch_khach(client, headers, khach, status="active")
        await _patch_khach(client, headers, khach, name="Tên mới")

        assert (await _deal(client, headers, deal["id"]))["stage"] == "new_lead"

    async def test_luu_lai_khach_da_luu_tru_khong_lam_gi_them(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        khach = await _create_client(client, headers)
        deal = await _create_deal(client, headers, "Một lần thôi", client_id=khach)
        await _patch_khach(client, headers, khach, status="archived")
        truoc = await _deal(client, headers, deal["id"])

        resp = await _patch_khach(client, headers, khach, status="archived", name="Đổi tên")

        assert resp.status_code == 200, resp.text
        sau = await _deal(client, headers, deal["id"])
        assert sau["closed_at"] == truoc["closed_at"]
        entries = (
            await client.get(f"/api/v1/deals/{deal['id']}/activity", headers=headers)
        ).json()["data"]
        assert len([e for e in entries if e["new_stage"] == "lost"]) == 1

    async def test_deal_tao_sau_khi_khach_da_luu_tru_khong_bi_dong_khi_luu_lai_khach(
        self, client: AsyncClient
    ) -> None:
        headers = await _auth(client)
        khach = await _create_client(client, headers)
        await _patch_khach(client, headers, khach, status="archived")
        moi = await _create_deal(client, headers, "Tạo sau khi lưu trữ", client_id=khach)

        resp = await _patch_khach(client, headers, khach, status="archived", name="Đổi tên")

        assert resp.status_code == 200, resp.text
        assert (await _deal(client, headers, moi["id"]))["stage"] == "new_lead"

    async def test_deal_da_xoa_cua_khach_khong_lam_hong_viec_luu_tru(
        self, client: AsyncClient
    ) -> None:
        headers = await _auth(client)
        khach = await _create_client(client, headers)
        da_xoa = await _create_deal(client, headers, "Đã xóa", client_id=khach)
        con_lai = await _create_deal(client, headers, "Còn lại", client_id=khach)
        xoa = await client.delete(f"/api/v1/deals/{da_xoa['id']}", headers=headers)
        assert xoa.status_code == 200, xoa.text

        resp = await _patch_khach(client, headers, khach, status="archived")

        assert resp.status_code == 200, resp.text
        assert (await _deal(client, headers, con_lai["id"]))["stage"] == "lost"

    async def test_bo_luu_tru_khong_hoi_sinh_du_an_da_dong(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        khach = await _create_client(client, headers)
        deal = await _create_deal(client, headers, "Đã bị đóng", client_id=khach)
        await _patch_khach(client, headers, khach, status="archived")

        resp = await _patch_khach(client, headers, khach, status="prospect")

        assert resp.status_code == 200, resp.text
        assert (await _deal(client, headers, deal["id"]))["stage"] == "lost"


class TestTienVaTyLeThang:
    async def test_phan_chua_thu_khong_con_la_con_phai_thu_va_deal_tinh_la_thua(
        self, client: AsyncClient
    ) -> None:
        headers, _ = await _seed(client)
        deals = (await client.get("/api/v1/deals", headers=headers)).json()["data"]
        deal = deals[0]
        truoc = (await client.get("/api/v1/analytics/revenue", headers=headers)).json()["data"]
        assert float(truoc["milestone_outstanding"]) > 0

        resp = await _patch_khach(client, headers, deal["client_id"], status="archived")

        assert resp.status_code == 200, resp.text
        sau = (await client.get("/api/v1/analytics/revenue", headers=headers)).json()["data"]
        assert float(sau["milestone_outstanding"]) == 0
        thang = (await client.get("/api/v1/analytics/win-rate", headers=headers)).json()["data"]
        assert thang["lost"] == 1 and thang["won"] == 0
