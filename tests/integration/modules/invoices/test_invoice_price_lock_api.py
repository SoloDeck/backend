"""Giá của hóa đơn xuất theo một MỐC của hợp đồng bị KHÓA ở bước chỉnh sửa/soạn hóa đơn.

Giá đã chốt trong hợp đồng. Cho gõ lại số tiền hay VAT ở hóa đơn là cho hóa đơn lệch hợp đồng —
hợp đồng có cũng như không. Muốn đổi giá thì phải thỏa thuận lại hợp đồng, không phải sửa hóa đơn.

Chạy trên PostgreSQL thật, seed đi đúng luồng thật (báo giá → chốt → hợp đồng ký → task thu tiền →
hóa đơn từ task) chứ không tự tạo hóa đơn: cái cần kiểm là hóa đơn NỐI VỚI một mốc.
"""

from datetime import date, timedelta

from httpx import AsyncClient

from tests.integration.modules.tasks.test_payment_task_invoice import _seed

GIA_MOC = "12000000.00"  # hạng mục "Dựng giao diện" trong báo giá seed


async def _hoa_don_tu_moc(client: AsyncClient) -> tuple[dict, dict]:
    headers, task_id = await _seed(client)
    resp = await client.post(f"/api/v1/tasks/{task_id}/invoice", headers=headers)
    assert resp.status_code == 201, resp.text
    invoice = resp.json()["data"]
    assert invoice["subtotal"] == GIA_MOC and invoice["status"] == "draft"
    return headers, invoice


async def _lay(client: AsyncClient, headers: dict, invoice_id: str) -> dict:
    resp = await client.get(f"/api/v1/invoices/{invoice_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _dong(unit_price: str) -> list[dict]:
    return [{"description": "Dựng giao diện", "quantity": "1", "unit_price": unit_price}]


async def test_khong_sua_duoc_so_tien_cua_hoa_don_thuoc_mot_moc(client: AsyncClient) -> None:
    headers, invoice = await _hoa_don_tu_moc(client)

    resp = await client.patch(
        f"/api/v1/invoices/{invoice['id']}", json={"subtotal": "13000000"}, headers=headers
    )

    assert resp.status_code == 409, resp.text
    assert "hợp đồng" in resp.text
    after = await _lay(client, headers, invoice["id"])
    assert after["subtotal"] == GIA_MOC and after["total"] == GIA_MOC


async def test_khong_sua_duoc_dong_hang_de_doi_gia(client: AsyncClient) -> None:
    headers, invoice = await _hoa_don_tu_moc(client)

    resp = await client.patch(
        f"/api/v1/invoices/{invoice['id']}",
        json={"line_items": _dong("13000000")},
        headers=headers,
    )

    assert resp.status_code == 409, resp.text
    assert (await _lay(client, headers, invoice["id"]))["total"] == GIA_MOC


async def test_khong_doi_duoc_vat(client: AsyncClient) -> None:
    headers, invoice = await _hoa_don_tu_moc(client)

    resp = await client.patch(
        f"/api/v1/invoices/{invoice['id']}", json={"tax_rate": "0.08"}, headers=headers
    )

    assert resp.status_code == 409, resp.text
    after = await _lay(client, headers, invoice["id"])
    assert after["tax_rate"] in ("0", "0.0000") or float(after["tax_rate"]) == 0
    assert after["total"] == GIA_MOC


async def test_gui_lai_dung_so_tien_cu_thi_van_luu_duoc_han_thanh_toan_va_loi_nhan(
    client: AsyncClient,
) -> None:
    """Web luôn gửi lại cả bộ số tiền khi lưu; khóa giá không được làm hỏng việc lưu bình thường."""
    headers, invoice = await _hoa_don_tu_moc(client)
    han_moi = (date.today() + timedelta(days=30)).isoformat()

    resp = await client.patch(
        f"/api/v1/invoices/{invoice['id']}",
        json={
            "due_date": han_moi,
            "subtotal": "12000000",
            "tax_rate": "0",
            "line_items": _dong("12000000"),
            "notes": "Hóa đơn: Thanh toán đợt 1\n\nTổng số tiền cần thanh toán là 12.000.000 ₫.",
        },
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["due_date"] == han_moi
    assert data["total"] == GIA_MOC
    assert "12.000.000" in data["notes"]


async def test_loi_nhan_ghi_so_tien_khac_thi_khong_luu_duoc(client: AsyncClient) -> None:
    """Chữ cũng không được ghi giá khác hợp đồng: chặn ngay khi lưu, không đợi tới lúc gửi."""
    headers, invoice = await _hoa_don_tu_moc(client)

    resp = await client.patch(
        f"/api/v1/invoices/{invoice['id']}",
        json={"notes": "Hóa đơn: Đợt 1\n\nTổng cộng 11.000.000 ₫, cảm ơn anh."},
        headers=headers,
    )

    assert resp.status_code == 409, resp.text
    assert "11.000.000" in resp.text
    assert (await _lay(client, headers, invoice["id"]))["notes"] in (None, "")


async def test_loi_nhan_ghi_don_vi_tat_cung_bi_chan(client: AsyncClient) -> None:
    headers, invoice = await _hoa_don_tu_moc(client)

    resp = await client.patch(
        f"/api/v1/invoices/{invoice['id']}",
        json={"notes": "Chỉ cần 10tr là xong nhé."},
        headers=headers,
    )

    assert resp.status_code == 409, resp.text


async def test_so_tran_trong_loi_nhan_khong_bi_coi_la_tien(client: AsyncClient) -> None:
    """Điện thoại, ngày tháng, mã đợt không phải tiền — không thì ai cũng bị chặn oan."""
    headers, invoice = await _hoa_don_tu_moc(client)

    resp = await client.patch(
        f"/api/v1/invoices/{invoice['id']}",
        json={"notes": "Hóa đơn: Đợt 1\n\nGọi 0352015349 trước 16/10/2026 nhé, đợt 2 sau."},
        headers=headers,
    )

    assert resp.status_code == 200, resp.text


async def test_ten_hoa_don_o_dong_dau_khong_bi_soi_nhu_loi_nhan(client: AsyncClient) -> None:
    """`Hóa đơn: <tên>` là dòng nội bộ web lưu ké trong notes, khách không thấy."""
    headers, invoice = await _hoa_don_tu_moc(client)

    resp = await client.patch(
        f"/api/v1/invoices/{invoice['id']}",
        json={"notes": "Hóa đơn: Đợt 1 - 5tr\n\nCảm ơn anh."},
        headers=headers,
    )

    assert resp.status_code == 200, resp.text


async def test_hoa_don_khong_thuoc_mot_nao_thi_van_sua_duoc_so_tien(client: AsyncClient) -> None:
    """Không có mốc nào nối tới thì không có hợp đồng để bám — giữ nguyên hành vi cũ."""
    headers, invoice = await _hoa_don_tu_moc(client)
    le = await client.post(
        "/api/v1/invoices",
        json={
            "client_id": invoice["client_id"],
            "deal_id": invoice["deal_id"],
            "due_date": (date.today() + timedelta(days=14)).isoformat(),
            "subtotal": "5000000",
        },
        headers=headers,
    )
    assert le.status_code == 201, le.text

    resp = await client.patch(
        f"/api/v1/invoices/{le.json()['data']['id']}",
        json={"subtotal": "6000000"},
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["total"] == "6000000.00"


async def test_loi_nhan_duoc_ghi_tam_tinh_thue_va_tong_cua_hoa_don(client: AsyncClient) -> None:
    """Số khớp MỘT con số trên hóa đơn (tạm tính, thuế, tổng) thì cho qua; chỉ số lạ mới bị chặn."""
    headers, invoice = await _hoa_don_tu_moc(client)
    le = await client.post(
        "/api/v1/invoices",
        json={
            "client_id": invoice["client_id"],
            "deal_id": invoice["deal_id"],
            "due_date": (date.today() + timedelta(days=14)).isoformat(),
            "subtotal": "5000000",
            "tax_rate": "0.1",
        },
        headers=headers,
    )
    assert le.status_code == 201, le.text
    url = f"/api/v1/invoices/{le.json()['data']['id']}"

    for chu in ("Tạm tính 5.000.000 ₫.", "Thuế 500.000 ₫.", "Tổng cộng 5.500.000 ₫."):
        ok = await client.patch(url, json={"notes": chu}, headers=headers)
        assert ok.status_code == 200, (chu, ok.text)

    sai = await client.patch(url, json={"notes": "Tổng cộng 6.000.000 ₫."}, headers=headers)
    assert sai.status_code == 409, sai.text
