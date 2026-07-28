"""Integration coverage for analytics endpoints added in Phase 6."""

from httpx import AsyncClient

from tests.integration.modules.clients.test_clients_api import _auth_headers


async def test_dashboard_returns_contract_shape(client: AsyncClient) -> None:
    headers = await _auth_headers(client)

    resp = await client.get("/api/v1/analytics/dashboard", headers=headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data) == {"total_clients", "active_deals", "total_revenue", "pending_invoices"}


async def test_revenue_pipeline_win_rate_top_clients_and_ai_usage_return_contract_shapes(
    client: AsyncClient,
) -> None:
    headers = await _auth_headers(client)

    revenue = await client.get(
        "/api/v1/analytics/revenue?period_type=monthly&from_date=2026-01-01&to_date=2026-12-31",
        headers=headers,
    )
    assert revenue.status_code == 200
    # Ba trường hoá đơn là hợp đồng BẮT BUỘC — phải còn nguyên. Các trường tiền-theo-mốc là
    # phần THÊM (openapi không khoá `additionalProperties`), nên kiểm bao hàm chứ không kiểm
    # bằng nhau: khoá chặt bằng `==` thì mỗi lần bổ sung số liệu là test đỏ vô cớ.  #Huynh
    assert {"total_invoiced", "total_collected", "total_outstanding"} <= set(
        revenue.json()["data"]
    )

    pipeline = await client.get(
        "/api/v1/analytics/pipeline?snapshot_date=2026-01-01", headers=headers
    )
    assert pipeline.status_code == 200
    assert isinstance(pipeline.json()["data"], list)

    win_rate = await client.get("/api/v1/analytics/win-rate", headers=headers)
    assert win_rate.status_code == 200
    assert set(win_rate.json()["data"]) == {"won", "lost", "win_rate"}

    top_clients = await client.get(
        "/api/v1/analytics/clients/top?limit=5&metric=total_collected", headers=headers
    )
    assert top_clients.status_code == 200
    assert isinstance(top_clients.json()["data"], list)

    ai_usage = await client.get("/api/v1/analytics/ai-usage", headers=headers)
    assert ai_usage.status_code == 200
    # Trước đây chỉ trả về số lượt đã dùng — người dùng thấy "đã gọi 12 lần" nhưng KHÔNG
    # biết mình còn bao nhiêu lượt, cũng không biết gói của mình có được dùng AI không.
    # Màn "Gói đăng ký" cần đủ 5 trường dưới để vẽ được vòng tròn hạn mức.  #Huynh
    assert set(ai_usage.json()["data"]) == {
        "generations_used",
        "estimated_cost_usd",
        "limit",
        "remaining",
        "can_use_ai",
        "period_start",
        "period_end",
    }


async def test_revenue_aggregates_paid_invoices(client: AsyncClient) -> None:
    headers = await _auth_headers(client)

    # Seed: create client → deal → invoice → send → pay in full
    client_obj = (
        await client.post(
            "/api/v1/clients",
            json={"name": "Acme", "email": "acme@example.com", "type": "company"},
            headers=headers,
        )
    ).json()["data"]
    deal = (
        await client.post(
            "/api/v1/deals",
            json={"client_id": client_obj["id"], "title": "Analytics test deal"},
            headers=headers,
        )
    ).json()["data"]
    inv = (
        await client.post(
            "/api/v1/invoices",
            json={
                "client_id": client_obj["id"],
                "deal_id": deal["id"],
                "subtotal": "500.00",
                "tax_rate": "0",
                "due_date": "2026-12-31",
            },
            headers=headers,
        )
    ).json()["data"]
    await client.post(f"/api/v1/invoices/{inv['id']}/send", headers=headers)
    await client.post(
        f"/api/v1/invoices/{inv['id']}/payments",
        json={"amount": "500.00", "payment_date": "2026-01-01", "payment_method": "bank_transfer"},
        headers=headers,
    )

    # Now check revenue aggregate includes this paid invoice
    resp = await client.get("/api/v1/analytics/revenue", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert float(data["total_collected"]) >= 500.0
    assert float(data["total_invoiced"]) >= 500.0


async def test_revenue_monthly_returns_continuous_series(client: AsyncClient) -> None:
    """Chuỗi tháng phải LIỀN MẠCH: freelancer mới chưa hoá đơn nào vẫn nhận đủ N cột 0,
    để biểu đồ frontend không bị đứt."""
    headers = await _auth_headers(client)
    resp = await client.get("/api/v1/analytics/revenue/monthly?months=6", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 6
    assert set(data[0]) == {"month", "invoiced", "collected"}
    # Liền mạch: mỗi tháng cách tháng trước đúng 1 tháng.
    months = [row["month"] for row in data]
    assert months == sorted(months)


async def test_revenue_monthly_buckets_a_paid_invoice(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    client_obj = (
        await client.post(
            "/api/v1/clients",
            json={"name": "Monthly Co", "email": "monthly@example.com", "type": "company"},
            headers=headers,
        )
    ).json()["data"]
    deal = (
        await client.post(
            "/api/v1/deals",
            json={"client_id": client_obj["id"], "title": "Monthly deal"},
            headers=headers,
        )
    ).json()["data"]
    inv = (
        await client.post(
            "/api/v1/invoices",
            json={
                "client_id": client_obj["id"],
                "deal_id": deal["id"],
                "subtotal": "700.00",
                "tax_rate": "0",
                "issue_date": "2026-07-10",
                "due_date": "2026-08-10",
            },
            headers=headers,
        )
    ).json()["data"]
    await client.post(f"/api/v1/invoices/{inv['id']}/send", headers=headers)

    resp = await client.get("/api/v1/analytics/revenue/monthly?months=24", headers=headers)
    data = resp.json()["data"]
    july = next((r for r in data if r["month"] == "2026-07"), None)
    assert july is not None, "tháng 7/2026 phải nằm trong cửa sổ 24 tháng"
    assert float(july["invoiced"]) >= 700.0


async def test_revenue_monthly_rejects_out_of_range_months(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    assert (await client.get("/api/v1/analytics/revenue/monthly?months=99", headers=headers)).status_code == 422


async def test_revenue_monthly_unauthenticated_returns_401(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/analytics/revenue/monthly")).status_code == 401


async def test_revenue_tinh_theo_moc_thanh_toan_cua_hop_dong_da_ky(client: AsyncClient) -> None:
    """Tiền trên bảng doanh thu đi theo MỐC THANH TOÁN, không theo hoá đơn.

    Vì sao: từ Phase B, hoàn thành dự án đo bằng task "Thu tiền:" chứ không đòi hoá đơn.
    Đo trên bản chạy thật: phễu hiện 7 deal đang triển khai trị giá 1,24 tỷ mà bảng doanh
    thu ghi "Còn phải thu: 0 đ" — màn hình bảo freelancer không còn gì để thu.

    Bài này dựng nguyên chuỗi thật: khách → deal → báo giá 50/50 chốt giá 100tr → ký hợp
    đồng (sinh task thu tiền) → tick MỘT mốc, rồi đòi bảng doanh thu ra đúng 50/50.  #Huynh
    """
    headers = await _auth_headers(client)

    client_obj = (
        await client.post(
            "/api/v1/clients",
            json={"name": "Khách Mốc", "email": "moc@example.com", "type": "company"},
            headers=headers,
        )
    ).json()["data"]
    deal = (
        await client.post(
            "/api/v1/deals",
            json={"client_id": client_obj["id"], "title": "Deal theo mốc"},
            headers=headers,
        )
    ).json()["data"]

    proposal = (
        await client.post(
            "/api/v1/proposals",
            json={
                "deal_id": deal["id"],
                "content": {
                    "title": "Báo giá theo mốc",
                    "payment_milestones": [
                        {"label": "Đặt cọc khi ký hợp đồng", "percent": 50},
                        {"label": "Thanh toán khi bàn giao", "percent": 50},
                    ],
                },
            },
            headers=headers,
        )
    ).json()["data"]

    priced = await client.patch(
        f"/api/v1/proposals/{proposal['id']}/price",
        json={"price": "100000000"},
        headers=headers,
    )
    assert priced.status_code == 200, priced.text

    for status in ("sent", "accepted"):
        resp = await client.patch(
            f"/api/v1/proposals/{proposal['id']}/status",
            json={"status": status},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

    contract = (
        await client.post(
            "/api/v1/contracts",
            json={
                "deal_id": deal["id"],
                "proposal_id": proposal["id"],
                "client_id": client_obj["id"],
                "content": {},
            },
            headers=headers,
        )
    ).json()["data"]
    for status in ("pending_signatures", "active"):
        resp = await client.patch(
            f"/api/v1/contracts/{contract['id']}/status",
            json={"status": status},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

    # Ký hợp đồng xong là đã có project + 2 task "Thu tiền:".
    projects = (await client.get("/api/v1/projects", headers=headers)).json()["data"]
    project_id = next(p["id"] for p in projects if p["deal_id"] == deal["id"])
    tasks = (
        await client.get(f"/api/v1/projects/{project_id}/tasks", headers=headers)
    ).json()["data"]
    payment_tasks = [t for t in tasks if t["title"].startswith("Thu tiền:")]
    assert len(payment_tasks) == 2, [t["title"] for t in tasks]

    # Chưa thu đồng nào: tất cả nằm ở "còn phải thu".
    before = (await client.get("/api/v1/analytics/revenue", headers=headers)).json()["data"]
    assert float(before["total_contracted"]) == 100_000_000
    assert float(before["milestone_collected"]) == 0
    assert float(before["milestone_outstanding"]) == 100_000_000
    assert before["milestones_pending"] == 2

    # Tick mốc đặt cọc → thu đúng một nửa.
    ticked = await client.patch(
        f"/api/v1/tasks/{payment_tasks[0]['id']}",
        json={"status": "done"},
        headers=headers,
    )
    assert ticked.status_code == 200, ticked.text

    after = (await client.get("/api/v1/analytics/revenue", headers=headers)).json()["data"]
    assert float(after["milestone_collected"]) == 50_000_000
    assert float(after["milestone_outstanding"]) == 50_000_000
    assert after["milestones_pending"] == 1

    # Và khách đó phải nổi lên bảng xếp hạng kèm số còn nợ.
    top = (await client.get("/api/v1/analytics/clients/top", headers=headers)).json()["data"]
    row = next(c for c in top if c["client_id"] == client_obj["id"])
    assert float(row["revenue"]) == 50_000_000
    assert float(row["outstanding"]) == 50_000_000
    assert row["deal_count"] == 1
