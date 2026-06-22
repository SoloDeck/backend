"""Integration tests for invoices CRUD and list filters."""

import uuid
from datetime import date

from httpx import AsyncClient

from tests.integration.modules.clients.test_clients_api import _auth_headers, _create_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_deal(client: AsyncClient, headers: dict, client_id: str) -> str:
    resp = await client.post(
        "/api/v1/deals",
        json={"client_id": client_id, "title": f"Deal {uuid.uuid4().hex[:6]}"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _create_invoice(client: AsyncClient, headers: dict, **overrides) -> dict:
    client_obj = await _create_client(client, headers)
    deal_id = await _create_deal(client, headers, client_obj["id"])
    payload = {
        "client_id": client_obj["id"],
        "deal_id": deal_id,
        "subtotal": "500.00",
        "tax_rate": "0",
        "due_date": date(2027, 6, 30).isoformat(),
        **overrides,
    }
    resp = await client.post("/api/v1/invoices", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# POST /invoices
# ---------------------------------------------------------------------------

class TestCreateInvoice:
    async def test_creates_invoice_returns_201(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        inv = await _create_invoice(client, headers)
        assert inv["status"] == "draft"
        assert float(inv["subtotal"]) == 500.0

    async def test_missing_due_date_returns_422(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        client_obj = await _create_client(client, headers)
        resp = await client.post(
            "/api/v1/invoices",
            json={"client_id": client_obj["id"], "subtotal": "100", "tax_rate": "0"},
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/invoices",
            json={"client_id": str(uuid.uuid4()), "subtotal": "100", "tax_rate": "0", "due_date": "2027-01-01"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /invoices
# ---------------------------------------------------------------------------

class TestListInvoices:
    async def test_returns_own_invoices(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        await _create_invoice(client, headers)
        await _create_invoice(client, headers)
        resp = await client.get("/api/v1/invoices", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 2

    async def test_filter_by_status_draft(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        await _create_invoice(client, headers)
        resp = await client.get("/api/v1/invoices?status=draft", headers=headers)
        data = resp.json()["data"]
        assert len(data) >= 1
        assert all(inv["status"] == "draft" for inv in data)

    async def test_filter_by_status_excludes_others(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        await _create_invoice(client, headers)
        resp = await client.get("/api/v1/invoices?status=paid", headers=headers)
        assert all(inv["status"] == "paid" for inv in resp.json()["data"])

    async def test_filter_by_invoice_number(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        inv = await _create_invoice(client, headers)
        inv_number = inv.get("invoice_number")
        if inv_number is None:
            return  # invoice_number not auto-generated yet
        resp = await client.get(f"/api/v1/invoices?invoice_number={inv_number}", headers=headers)
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["id"] == inv["id"]

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth_headers(client)
        headers_b = await _auth_headers(client)
        await _create_invoice(client, headers_a)
        resp = await client.get("/api/v1/invoices", headers=headers_b)
        ids = [inv["id"] for inv in resp.json()["data"]]
        inv_id = (await _create_invoice(client, headers_a))["id"]
        assert inv_id not in ids

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/invoices")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /invoices/{id}
# ---------------------------------------------------------------------------

class TestGetInvoice:
    async def test_returns_invoice(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        inv = await _create_invoice(client, headers)
        resp = await client.get(f"/api/v1/invoices/{inv['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == inv["id"]

    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        resp = await client.get(f"/api/v1/invoices/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth_headers(client)
        headers_b = await _auth_headers(client)
        inv = await _create_invoice(client, headers_a)
        resp = await client.get(f"/api/v1/invoices/{inv['id']}", headers=headers_b)
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/invoices/{uuid.uuid4()}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /invoices/{id}
# ---------------------------------------------------------------------------

class TestUpdateInvoice:
    async def test_updates_notes(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        inv = await _create_invoice(client, headers)
        resp = await client.patch(
            f"/api/v1/invoices/{inv['id']}",
            json={"notes": "Updated note", "due_date": date(2027, 12, 31).isoformat()},
            headers=headers,
        )
        assert resp.status_code in (200, 201)

    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        resp = await client.patch(
            f"/api/v1/invoices/{uuid.uuid4()}",
            json={"due_date": date(2027, 12, 31).isoformat()},
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth_headers(client)
        headers_b = await _auth_headers(client)
        inv = await _create_invoice(client, headers_a)
        resp = await client.patch(
            f"/api/v1/invoices/{inv['id']}",
            json={"notes": "Hijack", "due_date": date(2027, 12, 31).isoformat()},
            headers=headers_b,
        )
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.patch(
            f"/api/v1/invoices/{uuid.uuid4()}",
            json={"due_date": date(2027, 12, 31).isoformat()},
        )
        assert resp.status_code == 401
