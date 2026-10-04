"""Dự án KHÔNG THÀNH CÔNG: lý do được lưu lại, và phần CHƯA thu của nó không còn là "còn phải thu".

Trước đây không có đường nào đưa deal vào giai đoạn `lost` (nút "Loại bỏ dự án" chỉ xóa mềm) nên
mẫu số của tỷ lệ thắng luôn rỗng và tỷ lệ luôn 100%. Chạy trên PostgreSQL thật, seed đi đúng luồng
thật (báo giá → chốt → hợp đồng ký → task thu tiền) vì cái cần kiểm là tiền của các mốc.
"""

import uuid

from httpx import AsyncClient

from tests.integration.modules.clients.test_clients_api import _auth_headers, _create_client
from tests.integration.modules.tasks.test_payment_task_invoice import _seed


async def _deal_va_moc(client: AsyncClient) -> tuple[dict, str, list[dict]]:
    """Một deal đã ký hợp đồng với hai mốc 12 triệu + 8 triệu. Trả (headers, deal_id, các mốc)."""
    headers, _ = await _seed(client)
    deal_id = (await client.get("/api/v1/deals", headers=headers)).json()["data"][0]["id"]
    projects = (await client.get("/api/v1/projects", headers=headers)).json()["data"]
    project_id = next(p["id"] for p in projects if p["deal_id"] == deal_id)
    url = f"/api/v1/projects/{project_id}/tasks"
    tasks = (await client.get(url, headers=headers)).json()["data"]
    return headers, deal_id, [t for t in tasks if t["billing_amount"] is not None]


async def _tick(client: AsyncClient, headers: dict, task_id: str) -> None:
    resp = await client.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"}, headers=headers)
    assert resp.status_code == 200, resp.text


async def _mat_deal(client: AsyncClient, headers: dict, deal_id: str, reason: str | None):
    body: dict = {"target_stage": "lost"}
    if reason is not None:
        body["reason"] = reason
    return await client.post(f"/api/v1/deals/{deal_id}/stage", json=body, headers=headers)


async def _tien(client: AsyncClient, headers: dict) -> dict:
    resp = await client.get("/api/v1/analytics/revenue", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


class TestLyDo:
    async def test_thieu_ly_do_van_danh_dau_duoc_de_client_cu_khong_hong(
        self, client: AsyncClient
    ) -> None:
        """App di động vốn cho bấm "Đã mất" mà không gửi lý do; API không được làm hỏng nó.

        Web mới là nơi bắt buộc nhập (hộp "Loại bỏ dự án"). Lý do rỗng hay chỉ khoảng trắng đều
        lưu thành "không có", không phải chuỗi rỗng.
        """
        for thieu in (None, "", "   "):
            headers, deal_id, _ = await _deal_va_moc(client)

            resp = await _mat_deal(client, headers, deal_id, thieu)

            assert resp.status_code == 200, (thieu, resp.text)
            deal = resp.json()["data"]
            assert deal["stage"] == "lost"
            assert deal["lost_reason"] is None, repr(thieu)
            assert deal["closed_at"] is not None

    async def test_co_ly_do_thi_luu_ly_do_va_ngay_dong(self, client: AsyncClient) -> None:
        headers, deal_id, _ = await _deal_va_moc(client)

        resp = await _mat_deal(client, headers, deal_id, "  Khách chọn bên khác rẻ hơn  ")

        assert resp.status_code == 200, resp.text
        deal = resp.json()["data"]
        assert deal["stage"] == "lost"
        assert deal["lost_reason"] == "Khách chọn bên khác rẻ hơn"  # đã bỏ khoảng trắng thừa
        assert deal["closed_at"] is not None
        # Đọc lại từ DB, không tin phản hồi của chính lệnh ghi.
        again = (await client.get(f"/api/v1/deals/{deal_id}", headers=headers)).json()["data"]
        assert again["lost_reason"] == "Khách chọn bên khác rẻ hơn"

    async def test_ly_do_nam_trong_nhat_ky_cua_deal(self, client: AsyncClient) -> None:
        headers, deal_id, _ = await _deal_va_moc(client)
        await _mat_deal(client, headers, deal_id, "Ngân sách không đủ")

        entries = (await client.get(f"/api/v1/deals/{deal_id}/activity", headers=headers)).json()[
            "data"
        ]

        loi = [e for e in entries if e["new_stage"] == "lost"]
        assert len(loi) == 1
        assert "Ngân sách không đủ" in loi[0]["description"]

    async def test_khong_co_ly_do_thi_nhat_ky_khong_ghi_ly_do(self, client: AsyncClient) -> None:
        headers, deal_id, _ = await _deal_va_moc(client)
        await _mat_deal(client, headers, deal_id, None)

        entries = (await client.get(f"/api/v1/deals/{deal_id}/activity", headers=headers)).json()[
            "data"
        ]

        loi = [e for e in entries if e["new_stage"] == "lost"]
        assert len(loi) == 1
        assert "Lý do" not in loi[0]["description"]

    async def test_ly_do_qua_dai_bi_tu_choi(self, client: AsyncClient) -> None:
        headers, deal_id, _ = await _deal_va_moc(client)

        resp = await _mat_deal(client, headers, deal_id, "x" * 1001)

        assert resp.status_code == 422, resp.text

    async def test_chuyen_giai_doan_binh_thuong_thi_bo_qua_ly_do(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        khach = await _create_client(client, headers)
        deal = (
            await client.post(
                "/api/v1/deals",
                json={"client_id": khach["id"], "title": f"Deal {uuid.uuid4().hex[:6]}"},
                headers=headers,
            )
        ).json()["data"]

        resp = await client.post(
            f"/api/v1/deals/{deal['id']}/stage",
            json={"target_stage": "qualified", "reason": "ghi chú thừa"},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["lost_reason"] is None

    async def test_deal_da_that_bai_roi_thi_khong_doi_lai_duoc(self, client: AsyncClient) -> None:
        headers, deal_id, _ = await _deal_va_moc(client)
        await _mat_deal(client, headers, deal_id, "Khách im lặng")

        resp = await client.post(
            f"/api/v1/deals/{deal_id}/stage", json={"target_stage": "active"}, headers=headers
        )

        assert resp.status_code == 409, resp.text


class TestKhoLuuTruKhongThanhCong:
    async def test_liet_ke_deal_that_bai_kem_ly_do(self, client: AsyncClient) -> None:
        headers, deal_id, _ = await _deal_va_moc(client)
        await _mat_deal(client, headers, deal_id, "Khách chọn bên khác")

        resp = await client.get(
            "/api/v1/deals", params={"stage": "lost", "sort_by": "closed_at"}, headers=headers
        )

        rows = resp.json()["data"]
        assert [r["id"] for r in rows] == [deal_id]
        assert rows[0]["lost_reason"] == "Khách chọn bên khác"

    async def test_xoa_vinh_vien_thi_bien_khoi_danh_sach_va_ty_le(
        self, client: AsyncClient
    ) -> None:
        headers, deal_id, _ = await _deal_va_moc(client)
        await _mat_deal(client, headers, deal_id, "Khách im lặng")
        win = await client.get("/api/v1/analytics/win-rate", headers=headers)
        assert win.json()["data"]["lost"] == 1

        xoa = await client.delete(f"/api/v1/deals/{deal_id}", headers=headers)

        assert xoa.status_code == 200, xoa.text
        lost = await client.get("/api/v1/deals", params={"stage": "lost"}, headers=headers)
        listed = lost.json()
        assert listed["data"] == []
        win = await client.get("/api/v1/analytics/win-rate", headers=headers)
        assert win.json()["data"]["lost"] == 0


class TestTienCuaDealThatBai:
    async def test_phan_chua_thu_khong_con_la_con_phai_thu(self, client: AsyncClient) -> None:
        headers, deal_id, moc = await _deal_va_moc(client)
        assert len(moc) == 2
        truoc = await _tien(client, headers)
        assert float(truoc["total_contracted"]) == 20_000_000
        assert float(truoc["milestone_outstanding"]) == 20_000_000
        assert truoc["milestones_pending"] == 2

        await _mat_deal(client, headers, deal_id, "Khách chọn bên khác")
        sau = await _tien(client, headers)

        assert float(sau["milestone_outstanding"]) == 0
        assert sau["milestones_pending"] == 0
        assert float(sau["total_contracted"]) == 0
        assert float(sau["milestone_collected"]) == 0
        assert sau["signed_deals"] == 0

    async def test_phan_da_thu_van_la_tien_that(self, client: AsyncClient) -> None:
        """Khách cọc 12 triệu rồi bỏ: 12 triệu đã vào túi, 8 triệu còn lại sẽ không về."""
        headers, deal_id, moc = await _deal_va_moc(client)
        coc = next(m for m in moc if float(m["billing_amount"]) == 12_000_000)
        await _tick(client, headers, coc["id"])

        await _mat_deal(client, headers, deal_id, "Khách hủy sau khi cọc")
        tien = await _tien(client, headers)

        assert float(tien["milestone_collected"]) == 12_000_000
        assert float(tien["milestone_outstanding"]) == 0
        assert float(tien["total_contracted"]) == 12_000_000  # vẫn = Đã thu + Còn phải thu
        assert tien["milestones_pending"] == 0

    async def test_khong_dung_den_deal_dang_chay_khac(self, client: AsyncClient) -> None:
        """Chỉ deal thất bại bị loại phần chưa thu; deal khác của cùng người dùng giữ nguyên."""
        headers, deal_id, _ = await _deal_va_moc(client)
        # Deal thứ hai cùng người dùng, KHÔNG có hợp đồng nên không có mốc thu tiền nào.
        khach = await _create_client(client, headers)
        await client.post(
            "/api/v1/deals",
            json={"client_id": khach["id"], "title": "Deal khác"},
            headers=headers,
        )

        await _mat_deal(client, headers, deal_id, "Khách chọn bên khác")
        tien = await _tien(client, headers)

        assert float(tien["milestone_outstanding"]) == 0

    async def test_ty_le_thang_dem_deal_that_bai(self, client: AsyncClient) -> None:
        headers, deal_id, _ = await _deal_va_moc(client)
        await _mat_deal(client, headers, deal_id, "Khách chọn bên khác")

        thang = (await client.get("/api/v1/analytics/win-rate", headers=headers)).json()["data"]

        assert thang["lost"] == 1 and thang["won"] == 0
        assert thang["win_rate"] == 0

    async def test_gia_tri_deal_trung_binh_khong_tinh_deal_that_bai(
        self, client: AsyncClient
    ) -> None:
        headers, deal_id, _ = await _deal_va_moc(client)
        truoc = await _tien(client, headers)
        assert float(truoc["average_deal_value"]) == 20_000_000  # một deal, hai mốc 12 + 8 triệu

        await _mat_deal(client, headers, deal_id, "Khách chọn bên khác")
        sau = await _tien(client, headers)

        assert float(sau["average_deal_value"]) == 0
