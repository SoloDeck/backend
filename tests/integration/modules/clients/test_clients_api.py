"""Integration tests for clients API endpoints.

Covers status-filter regression: GET /clients?status=<value> must only return
clients matching that status.  Uses real PostgreSQL (rolled back per test).
"""

import uuid

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_payload(**overrides: object) -> dict:
    return {
        "email": f"user_{uuid.uuid4().hex[:8]}@example.com",
        "password": "Test@1234!",
        "full_name": "Test User",
        **overrides,
    }


async def _auth_headers(client: AsyncClient, **overrides: object) -> dict:
    resp = await client.post("/api/v1/auth/register", json=_register_payload(**overrides))
    assert resp.status_code == 201, resp.text
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _client_payload(**overrides: object) -> dict:
    return {
        "name": f"Client {uuid.uuid4().hex[:6]}",
        "email": f"client_{uuid.uuid4().hex[:6]}@example.com",
        "status": "prospect",
        "description": "A sample client for testing.",
        **overrides,
    }


async def _create_client(http: AsyncClient, headers: dict, **overrides: object) -> dict:
    resp = await http.post("/api/v1/clients", json=_client_payload(**overrides), headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# POST /clients  (create)
# ---------------------------------------------------------------------------


class TestCreateClient:
    async def test_success_returns_201(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        resp = await client.post("/api/v1/clients", json=_client_payload(), headers=headers)
        assert resp.status_code == 201
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["name"] is not None
        assert body["data"]["status"] == "prospect"
        assert body["data"]["description"] == "A sample client for testing."

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/clients", json=_client_payload())
        assert resp.status_code == 401

    async def test_missing_name_returns_422(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        resp = await client.post("/api/v1/clients", json={"email": "x@x.com"}, headers=headers)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /clients  (list + status filter)
# ---------------------------------------------------------------------------


class TestListClients:
    async def test_returns_all_own_clients(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        await _create_client(client, headers, status="prospect")
        await _create_client(client, headers, status="active")

        resp = await client.get("/api/v1/clients", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 2

    async def test_status_filter_prospect(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        await _create_client(client, headers, status="prospect")
        await _create_client(client, headers, status="active")
        await _create_client(client, headers, status="inactive")

        resp = await client.get("/api/v1/clients?status=prospect", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 1
        assert all(c["status"] == "prospect" for c in data)

    async def test_status_filter_active(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        await _create_client(client, headers, status="prospect")
        await _create_client(client, headers, status="active")

        resp = await client.get("/api/v1/clients?status=active", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 1
        assert all(c["status"] == "active" for c in data)

    async def test_status_filter_inactive(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        await _create_client(client, headers, status="prospect")
        await _create_client(client, headers, status="inactive")

        resp = await client.get("/api/v1/clients?status=inactive", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 1
        assert all(c["status"] == "inactive" for c in data)

    async def test_status_filter_archived(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        await _create_client(client, headers, status="archived")
        await _create_client(client, headers, status="prospect")

        resp = await client.get("/api/v1/clients?status=archived", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 1
        assert all(c["status"] == "archived" for c in data)

    async def test_status_filter_excludes_other_statuses(self, client: AsyncClient) -> None:
        """Core regression test: filtering by one status must not return others."""
        headers = await _auth_headers(client)
        await _create_client(client, headers, status="prospect")
        await _create_client(client, headers, status="active")
        await _create_client(client, headers, status="inactive")
        await _create_client(client, headers, status="archived")

        for status in ("prospect", "active", "inactive", "archived"):
            resp = await client.get(f"/api/v1/clients?status={status}", headers=headers)
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert all(c["status"] == status for c in data), (
                f"Expected only '{status}' clients, got statuses: "
                f"{[c['status'] for c in data]}"
            )

    async def test_no_filter_returns_all_statuses(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        await _create_client(client, headers, status="prospect")
        await _create_client(client, headers, status="active")

        resp = await client.get("/api/v1/clients", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        statuses = {c["status"] for c in data}
        assert "prospect" in statuses
        assert "active" in statuses

    async def test_name_search(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        await _create_client(client, headers, name="Nguyen Van Alpha")
        await _create_client(client, headers, name="Tran Thi Beta")

        resp = await client.get("/api/v1/clients?name=alpha", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 1
        assert all("alpha" in c["name"].lower() for c in data)

    async def test_email_search(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        unique = uuid.uuid4().hex[:8]
        await _create_client(client, headers, email=f"find_{unique}@example.com")
        await _create_client(client, headers, email=f"other_{unique}@example.com")

        resp = await client.get(f"/api/v1/clients?email=find_{unique}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert f"find_{unique}" in data[0]["email"]

    async def test_name_and_status_combined(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        await _create_client(client, headers, name="Combo Client", status="active")
        await _create_client(client, headers, name="Combo Client", status="inactive")

        resp = await client.get("/api/v1/clients?name=Combo&status=active", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 1
        assert all(c["status"] == "active" for c in data)

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/clients")
        assert resp.status_code == 401
        """User A's clients must not appear in User B's list."""
        headers_a = await _auth_headers(client)
        headers_b = await _auth_headers(client)

        created = await _create_client(client, headers_a, status="active")

        resp = await client.get("/api/v1/clients", headers=headers_b)
        assert resp.status_code == 200
        ids = [c["id"] for c in resp.json()["data"]]
        assert created["id"] not in ids


# ---------------------------------------------------------------------------
# GET /clients/{id}
# ---------------------------------------------------------------------------


class TestGetClient:
    async def test_success(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        created = await _create_client(client, headers)

        resp = await client.get(f"/api/v1/clients/{created['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == created["id"]

    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        resp = await client.get(f"/api/v1/clients/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    async def test_other_user_returns_404(self, client: AsyncClient) -> None:
        headers_a = await _auth_headers(client)
        headers_b = await _auth_headers(client)
        created = await _create_client(client, headers_a)

        resp = await client.get(f"/api/v1/clients/{created['id']}", headers=headers_b)
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/clients/{uuid.uuid4()}")
        assert resp.status_code == 401
