"""POST /tasks/{id}/invoice — xuất hóa đơn cho một khoản thu tiền.

Chạy trên PostgreSQL thật (rollback sau mỗi test) vì cả chuỗi đi qua 4 bảng: task → project
→ deal → hóa đơn. Mock hết thì chỉ còn kiểm rằng mình gọi đúng hàm mình vừa viết.

Seed đi qua ĐÚNG luồng thật (báo giá → chốt → hợp đồng → ghi nhận đã ký) chứ không tự tay
tạo task. Tự tạo task thì `billing_amount` là NULL, mà đó chính là thứ đang cần kiểm.
"""

from httpx import AsyncClient

from tests.integration.modules.clients.test_clients_api import _auth_headers

# Báo giá 20 triệu, hai hạng mục 12 + 8 triệu.
GIA_CHOT = "20000000.00"
PROPOSAL_CONTENT = {
    "project_overview": "Website bán hàng",
    # `pricing_detail.final_price` là thứ guard "chốt giá" của proposals đòi trước khi cho
    # chuyển sang `sent` — không có nó thì không gửi được, và do đó không chốt được.
    "pricing_detail": {"final_price": 20000000, "suggested": 20000000},
    "pricing_items": [
        {"label": "Dựng giao diện", "amount": 12000000, "due": "Khi ký hợp đồng"},
        {"label": "Nối cổng thanh toán", "amount": 8000000},
    ],
}


async def _seed(client: AsyncClient) -> tuple[dict, str]:
    """client → deal → báo giá ĐÃ CHỐT → hợp đồng ĐÃ KÝ → task thu tiền tự sinh."""
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

    contract = (
        await client.post(
            "/api/v1/contracts",
            json={
                "deal_id": deal["id"],
                "proposal_id": proposal["id"],
                "client_id": khach["id"],
                "content": {},
            },
            headers=headers,
        )
    ).json()["data"]
    for buoc in ("pending_signatures", "active"):
        chuyen = await client.patch(
            f"/api/v1/contracts/{contract['id']}/status",
            json={"status": buoc},
            headers=headers,
        )
        assert chuyen.status_code == 200, chuyen.text

    # Ghi nhận đã ký là project + task thu tiền đã có sẵn, không phải tự tạo.
    projects = (await client.get("/api/v1/projects", headers=headers)).json()["data"]
    project_id = next(p["id"] for p in projects if p["deal_id"] == deal["id"])
    tasks = (
        await client.get(f"/api/v1/projects/{project_id}/tasks", headers=headers)
    ).json()["data"]
    billing = [t for t in tasks if t["billing_amount"] is not None]
    assert len(billing) == 2, [t["title"] for t in tasks]
    # Tên task là NHÃN HẠNG MỤC nguyên văn, không còn tiền tố "Thu tiền:".
    assert billing[0]["title"] == "Dựng giao diện"

    return headers, billing[0]["id"]


async def test_xuat_hoa_don_dung_so_tien_cua_hang_muc(client: AsyncClient) -> None:
    """Số tiền do SERVER quyết từ `billing_amount`, client không gửi lên đồng nào."""
    headers, task_id = await _seed(client)

    resp = await client.post(f"/api/v1/tasks/{task_id}/invoice", headers=headers)

    assert resp.status_code == 201, resp.text
    invoice = resp.json()["data"]
    # Đúng số tiền của hạng mục "Dựng giao diện".
    assert invoice["total"] == "12000000.00"
    assert invoice["status"] == "draft"


async def test_doi_ten_task_van_xuat_duoc_hoa_don(client: AsyncClient) -> None:
    """ĐÂY LÀ CẢ ĐIỂM của việc thêm cột `billing_amount`.

    Bản cũ khớp mốc với TÊN TASK, nên freelancer sửa tên một chữ là không xuất được hóa đơn
    nữa — mà lỗi chỉ lộ ra đúng lúc họ định đi đòi tiền. Giờ tiền nằm trên cột, tên chỉ còn
    là nhãn.  #Huynh
    """
    headers, task_id = await _seed(client)
    doi_ten = await client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"title": "Dựng giao diện (đã sửa theo yêu cầu khách)"},
        headers=headers,
    )
    assert doi_ten.status_code == 200, doi_ten.text

    resp = await client.post(f"/api/v1/tasks/{task_id}/invoice", headers=headers)

    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["total"] == "12000000.00"


async def test_khong_xoa_duoc_task_thu_tien(client: AsyncClient) -> None:
    """Xoá một khoản phải thu là deal đóng lại được trong khi tiền chưa về."""
    headers, task_id = await _seed(client)

    resp = await client.delete(f"/api/v1/tasks/{task_id}", headers=headers)

    assert resp.status_code == 409, resp.text
    assert "thu tiền" in resp.json()["error"]["message"].lower()


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
    assert task["invoice"]["total"] == "12000000.00"


async def test_task_thuong_thi_tu_choi(client: AsyncClient) -> None:
    """Chỉ task thu tiền do hệ thống sinh mới xuất hóa đơn được — task "Sửa logo" không có
    số tiền nào cả, và đoán bừa một con số là tệ hơn từ chối."""
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
