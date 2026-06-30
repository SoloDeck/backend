"""Integration tests for clients API endpoints.

Covers status-filter regression: GET /clients?status=<value> must only return
clients matching that status.  Uses real PostgreSQL (rolled back per test).
"""

import uuid

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
                f"Expected only '{status}' clients, got statuses: " f"{[c['status'] for c in data]}"
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


class TestDealCount:
    async def test_deal_count_zero_for_new_client(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        created = await _create_client(client, headers)

        resp = await client.get(f"/api/v1/clients/{created['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["deal_count"] == 0

    async def test_deal_count_reflects_linked_deals(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        created = await _create_client(client, headers)
        client_id = created["id"]

        for i in range(3):
            resp = await client.post(
                "/api/v1/deals",
                json={"client_id": client_id, "title": f"Deal {i}"},
                headers=headers,
            )
            assert resp.status_code == 201, resp.text

        resp = await client.get(f"/api/v1/clients/{client_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["deal_count"] == 3

    async def test_deal_count_in_list(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        created = await _create_client(client, headers)
        client_id = created["id"]

        await client.post(
            "/api/v1/deals",
            json={"client_id": client_id, "title": "Deal A"},
            headers=headers,
        )

        resp = await client.get("/api/v1/clients", headers=headers)
        assert resp.status_code == 200
        matching = [c for c in resp.json()["data"] if c["id"] == client_id]
        assert len(matching) == 1
        assert matching[0]["deal_count"] == 1


# ---------------------------------------------------------------------------
# DELETE /clients/{id}
# ---------------------------------------------------------------------------


def _deal_payload(client_id: str, **overrides: object) -> dict:
    return {"client_id": client_id, "title": "Test Deal", **overrides}


def _invoice_payload(client_id: str, **overrides: object) -> dict:
    return {
        "client_id": client_id,
        "due_date": "2026-12-31",
        "currency": "VND",
        "subtotal": "1000000",
        **overrides,
    }


async def _create_contract(http, headers: dict, client_id: str) -> dict:
    """Create the minimal dependency chain (deal → proposal → contract) and return contract data."""
    deal = await http.post("/api/v1/deals", json=_deal_payload(client_id), headers=headers)
    assert deal.status_code == 201, deal.text
    deal_id = deal.json()["data"]["id"]

    proposal = await http.post(
        "/api/v1/proposals",
        json={"deal_id": deal_id, "content": {"body": "test"}},
        headers=headers,
    )
    assert proposal.status_code == 201, proposal.text
    proposal_id = proposal.json()["data"]["id"]

    # Contract requires an accepted proposal: draft → sent → accepted
    r = await http.patch(f"/api/v1/proposals/{proposal_id}/status", json={"status": "sent"}, headers=headers)
    assert r.status_code == 200, r.text
    r = await http.patch(f"/api/v1/proposals/{proposal_id}/status", json={"status": "accepted"}, headers=headers)
    assert r.status_code == 200, r.text

    contract = await http.post(
        "/api/v1/contracts",
        json={"deal_id": deal_id, "proposal_id": proposal_id, "client_id": client_id, "content": {}},
        headers=headers,
    )
    assert contract.status_code == 201, contract.text
    return contract.json()["data"]


class TestDeleteClient:
    async def test_clean_client_returns_200(self, client: AsyncClient) -> None:
        """Client with no transactions can be deleted."""
        headers = await _auth_headers(client)
        created = await _create_client(client, headers)

        resp = await client.delete(f"/api/v1/clients/{created['id']}", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["detail"] == "Client deleted"

    async def test_deleted_client_returns_404_on_get(self, client: AsyncClient) -> None:
        """Soft-deleted client is no longer retrievable."""
        headers = await _auth_headers(client)
        created = await _create_client(client, headers)

        await client.delete(f"/api/v1/clients/{created['id']}", headers=headers)

        resp = await client.get(f"/api/v1/clients/{created['id']}", headers=headers)
        assert resp.status_code == 404

    async def test_deleted_client_excluded_from_list(self, client: AsyncClient) -> None:
        """Soft-deleted client does not appear in GET /clients."""
        headers = await _auth_headers(client)
        created = await _create_client(client, headers)

        await client.delete(f"/api/v1/clients/{created['id']}", headers=headers)

        resp = await client.get("/api/v1/clients", headers=headers)
        assert resp.status_code == 200
        ids = [c["id"] for c in resp.json()["data"]]
        assert created["id"] not in ids

    async def test_client_with_deal_returns_409(self, client: AsyncClient) -> None:
        """Client that has a deal cannot be deleted."""
        headers = await _auth_headers(client)
        created = await _create_client(client, headers)

        deal_resp = await client.post(
            "/api/v1/deals",
            json=_deal_payload(created["id"]),
            headers=headers,
        )
        assert deal_resp.status_code == 201, deal_resp.text

        resp = await client.delete(f"/api/v1/clients/{created['id']}", headers=headers)
        assert resp.status_code == 409
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["code"] == "BUSINESS_RULE_VIOLATION"

    async def test_client_with_deal_error_message_is_descriptive(self, client: AsyncClient) -> None:
        """409 error message clearly explains why deletion was blocked."""
        headers = await _auth_headers(client)
        created = await _create_client(client, headers)
        await client.post(
            "/api/v1/deals",
            json=_deal_payload(created["id"]),
            headers=headers,
        )

        resp = await client.delete(f"/api/v1/clients/{created['id']}", headers=headers)
        assert resp.status_code == 409
        message = resp.json()["error"]["message"]
        assert "deals" in message.lower() or "invoices" in message.lower() or "contracts" in message.lower()

    async def test_client_with_soft_deleted_deal_still_returns_409(self, client: AsyncClient) -> None:
        """Soft-deleted deals still count — historical records block deletion."""
        headers = await _auth_headers(client)
        created = await _create_client(client, headers)

        deal_resp = await client.post(
            "/api/v1/deals",
            json=_deal_payload(created["id"]),
            headers=headers,
        )
        deal_id = deal_resp.json()["data"]["id"]

        # Soft-delete the deal
        del_resp = await client.delete(f"/api/v1/deals/{deal_id}", headers=headers)
        assert del_resp.status_code == 200, del_resp.text

        # Client still cannot be deleted
        resp = await client.delete(f"/api/v1/clients/{created['id']}", headers=headers)
        assert resp.status_code == 409

    async def test_client_with_invoice_returns_409(self, client: AsyncClient) -> None:
        """Client that has an invoice cannot be deleted."""
        headers = await _auth_headers(client)
        created = await _create_client(client, headers)

        # Invoices require a deal or contract — create the deal first
        deal_resp = await client.post(
            "/api/v1/deals",
            json=_deal_payload(created["id"]),
            headers=headers,
        )
        assert deal_resp.status_code == 201, deal_resp.text
        deal_id = deal_resp.json()["data"]["id"]

        inv_resp = await client.post(
            "/api/v1/invoices",
            json={**_invoice_payload(created["id"]), "deal_id": deal_id},
            headers=headers,
        )
        assert inv_resp.status_code == 201, inv_resp.text

        resp = await client.delete(f"/api/v1/clients/{created['id']}", headers=headers)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "BUSINESS_RULE_VIOLATION"

    async def test_client_with_soft_deleted_invoice_still_returns_409(self, client: AsyncClient) -> None:
        """Soft-deleted invoices still count — historical records block deletion."""
        headers = await _auth_headers(client)
        created = await _create_client(client, headers)

        deal_resp = await client.post(
            "/api/v1/deals",
            json=_deal_payload(created["id"]),
            headers=headers,
        )
        deal_id = deal_resp.json()["data"]["id"]

        inv_resp = await client.post(
            "/api/v1/invoices",
            json={**_invoice_payload(created["id"]), "deal_id": deal_id},
            headers=headers,
        )
        invoice_id = inv_resp.json()["data"]["id"]

        # Soft-delete the invoice
        del_resp = await client.delete(f"/api/v1/invoices/{invoice_id}", headers=headers)
        assert del_resp.status_code == 200, del_resp.text

        # Client still cannot be deleted
        resp = await client.delete(f"/api/v1/clients/{created['id']}", headers=headers)
        assert resp.status_code == 409

    async def test_client_with_contract_returns_409(self, client: AsyncClient) -> None:
        """Client that has a contract cannot be deleted."""
        headers = await _auth_headers(client)
        created = await _create_client(client, headers)

        await _create_contract(client, headers, created["id"])

        resp = await client.delete(f"/api/v1/clients/{created['id']}", headers=headers)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "BUSINESS_RULE_VIOLATION"

    async def test_client_with_soft_deleted_contract_still_returns_409(self, client: AsyncClient) -> None:
        """Soft-deleted contracts still count — historical records block deletion."""
        headers = await _auth_headers(client)
        created = await _create_client(client, headers)

        contract = await _create_contract(client, headers, created["id"])

        # Soft-delete the contract
        del_resp = await client.delete(f"/api/v1/contracts/{contract['id']}", headers=headers)
        assert del_resp.status_code == 200, del_resp.text

        # Client still cannot be deleted
        resp = await client.delete(f"/api/v1/clients/{created['id']}", headers=headers)
        assert resp.status_code == 409

    async def test_delete_nonexistent_client_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        resp = await client.delete(f"/api/v1/clients/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    async def test_delete_other_users_client_returns_404(self, client: AsyncClient) -> None:
        """User B cannot delete User A's client — gets 404, not 403."""
        headers_a = await _auth_headers(client)
        headers_b = await _auth_headers(client)
        created = await _create_client(client, headers_a)

        resp = await client.delete(f"/api/v1/clients/{created['id']}", headers=headers_b)
        assert resp.status_code == 404

    async def test_delete_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.delete(f"/api/v1/clients/{uuid.uuid4()}")
        assert resp.status_code == 401

    async def test_delete_twice_returns_404_on_second_call(self, client: AsyncClient) -> None:
        """Deleting an already-deleted client returns 404."""
        headers = await _auth_headers(client)
        created = await _create_client(client, headers)

        first = await client.delete(f"/api/v1/clients/{created['id']}", headers=headers)
        assert first.status_code == 200

        second = await client.delete(f"/api/v1/clients/{created['id']}", headers=headers)
        assert second.status_code == 404


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
