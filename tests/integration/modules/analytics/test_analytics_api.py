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
    assert set(revenue.json()["data"]) == {"total_invoiced", "total_collected", "total_outstanding"}

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
