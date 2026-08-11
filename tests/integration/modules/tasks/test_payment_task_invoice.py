"""POST /tasks/{id}/invoice — xuất hóa đơn cho một mốc thu tiền.

Chạy trên PostgreSQL thật (rollback sau mỗi test) vì cả chuỗi đi qua 4 bảng: task →
project → deal → proposal đã chốt, rồi mới ra hóa đơn. Mock hết thì chỉ còn kiểm rằng mình
gọi đúng hàm mình vừa viết.
"""

from httpx import AsyncClient

from tests.integration.modules.clients.test_clients_api import _auth_headers

# Báo giá 20 triệu, chia 50/50 → mỗi mốc 10 triệu.
GIA_CHOT = "20000000.00"
PROPOSAL_CONTENT = {
    "project_overview": "Website bán hàng",
    # `pricing_detail.final_price` là thứ guard "chốt giá" của proposals đòi trước khi cho
    # chuyển sang `sent` — không có nó thì không gửi được, và do đó không chốt được.
    "pricing_detail": {"final_price": 20000000},
    "payment_milestones": [
        {"label": "Đặt cọc khi ký hợp đồng", "percent": 50, "due": "Khi ký hợp đồng"},
        {"label": "Thanh toán khi bàn giao", "percent": 50, "due": "Khi nghiệm thu"},
    ],
}


async def _seed(client: AsyncClient) -> tuple[dict, str]:
    """Dựng client → deal (đã chốt giá) → báo giá ĐÃ CHẤP NHẬN → project → task thu tiền."""
    headers = await _auth_headers(client)

    khach = (
        await client.post(
            "/api/v1/clients",
            json={"name": "Công ty Nắng", "email": "nang@example.com", "type": "company"},
            headers=headers,
        )
    ).json()["data"]

    deal = (
        await client.post(
            "/api/v1/deals",
            json={
                "client_id": khach["id"],
                "title": "Website bán hàng",
                "estimated_value": GIA_CHOT,
            },
            headers=headers,
        )
    ).json()["data"]

    proposal = (
        await client.post(
            "/api/v1/proposals",
            json={"deal_id": deal["id"], "content": PROPOSAL_CONTENT},
            headers=headers,
        )
    ).json()["data"]
    # Báo giá chỉ đi được draft → sent → accepted, không nhảy thẳng (`_VALID_TRANSITIONS`).
    for buoc in ("sent", "accepted"):
        chuyen = await client.patch(
            f"/api/v1/proposals/{proposal['id']}/status",
            json={"status": buoc},
            headers=headers,
        )
        assert chuyen.status_code == 200, chuyen.text

    project = (
        await client.post(
            "/api/v1/projects",
            json={"deal_id": deal["id"], "name": "Website bán hàng"},
            headers=headers,
        )
    ).json()["data"]

    task = (
        await client.post(
            f"/api/v1/projects/{project['id']}/tasks",
            json={"title": "Thu tiền: Đặt cọc khi ký hợp đồng"},
            headers=headers,
        )
    ).json()["data"]

    return headers, task["id"]


async def test_xuat_hoa_don_dung_so_tien_cua_moc(client: AsyncClient) -> None:
    """Số tiền do SERVER tính từ báo giá, client không gửi lên đồng nào."""
    headers, task_id = await _seed(client)

    resp = await client.post(f"/api/v1/tasks/{task_id}/invoice", headers=headers)

    assert resp.status_code == 201, resp.text
    invoice = resp.json()["data"]
    # 50% của 20 triệu — đúng bộ tính của bảng doanh thu.
    assert invoice["total"] == "10000000.00"
    assert invoice["status"] == "draft"


async def test_bam_hai_lan_chi_ra_mot_hoa_don(client: AsyncClient) -> None:
    """Nút này nằm trong hộp thoại xác nhận nên bấm hai lần là chuyện chắc chắn xảy ra.
    Hai hóa đơn cho cùng một mốc thì khách trả hai lần hoặc không trả lần nào."""
    headers, task_id = await _seed(client)

    lan1 = await client.post(f"/api/v1/tasks/{task_id}/invoice", headers=headers)
    lan2 = await client.post(f"/api/v1/tasks/{task_id}/invoice", headers=headers)

    assert lan1.status_code == 201 and lan2.status_code == 201
    assert lan1.json()["data"]["id"] == lan2.json()["data"]["id"]

    tat_ca = (await client.get("/api/v1/invoices", headers=headers)).json()["data"]
    assert len(tat_ca) == 1, f"phải chỉ có 1 hóa đơn, đang có {len(tat_ca)}"


async def test_task_nho_duoc_hoa_don_cua_no(client: AsyncClient) -> None:
    """Đây là lý do phải thêm cột `tasks.invoice_id`: màn Công việc hiện nhãn trạng thái
    mà không phải đoán xem hóa đơn nào của mốc nào."""
    headers, task_id = await _seed(client)
    invoice = (await client.post(f"/api/v1/tasks/{task_id}/invoice", headers=headers)).json()[
        "data"
    ]

    task = (await client.get(f"/api/v1/tasks/{task_id}", headers=headers)).json()["data"]

    assert task["invoice"] is not None
    assert task["invoice"]["id"] == invoice["id"]
    assert task["invoice"]["status"] == "draft"
    assert task["invoice"]["total"] == "10000000.00"


async def test_task_thuong_thi_tu_choi(client: AsyncClient) -> None:
    """Chỉ mốc thu tiền do hệ thống sinh mới xuất hóa đơn được — task "Sửa logo" thì không
    có mốc nào để lấy số tiền, và đoán bừa một con số là tệ hơn từ chối."""
    headers, _ = await _seed(client)
    project = (await client.get("/api/v1/projects", headers=headers)).json()["data"][0]
    task_thuong = (
        await client.post(
            f"/api/v1/projects/{project['id']}/tasks",
            json={"title": "Sửa lại logo"},
            headers=headers,
        )
    ).json()["data"]

    resp = await client.post(f"/api/v1/tasks/{task_thuong['id']}/invoice", headers=headers)

    assert resp.status_code == 409, resp.text
    assert "thu tiền" in resp.json()["error"]["message"].lower()


async def test_task_chua_xuat_hoa_don_thi_invoice_la_none(client: AsyncClient) -> None:
    headers, task_id = await _seed(client)

    task = (await client.get(f"/api/v1/tasks/{task_id}", headers=headers)).json()["data"]

    assert task["invoice"] is None
