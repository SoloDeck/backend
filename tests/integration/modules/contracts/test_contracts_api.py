"""Integration tests for the Contracts API endpoints."""

import uuid
from unittest.mock import MagicMock, patch

from httpx import AsyncClient


def _reg(**overrides: object) -> dict:
    return {
        "email": f"user_{uuid.uuid4().hex[:8]}@example.com",
        "password": "Test@1234!",
        "full_name": "Test User",
        **overrides,
    }


async def _auth(client: AsyncClient) -> dict:
    resp = await client.post("/api/v1/auth/register", json=_reg())
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _create_client(http: AsyncClient, headers: dict) -> str:
    resp = await http.post(
        "/api/v1/clients",
        json={"name": "Acme Corp", "status": "prospect"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _create_deal(http: AsyncClient, headers: dict, client_id: str) -> str:
    resp = await http.post(
        "/api/v1/deals",
        json={"title": "Test deal", "client_id": client_id},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _create_accepted_proposal(http: AsyncClient, headers: dict, deal_id: str) -> str:
    resp = await http.post(
        "/api/v1/proposals",
        json={"deal_id": deal_id, "content": {"body": "proposal body"}},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    pid = resp.json()["data"]["id"]

    await http.patch(f"/api/v1/proposals/{pid}/status", json={"status": "sent"}, headers=headers)
    r = await http.patch(
        f"/api/v1/proposals/{pid}/status", json={"status": "accepted"}, headers=headers
    )
    assert r.status_code == 200, r.text
    return pid


async def _create_contract(
    http: AsyncClient, headers: dict, deal_id: str, proposal_id: str, client_id: str
) -> str:
    resp = await http.post(
        "/api/v1/contracts",
        json={
            "deal_id": deal_id,
            "proposal_id": proposal_id,
            "client_id": client_id,
            "content": {"title": "Service Agreement"},
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


# ---------------------------------------------------------------------------
# GET /contracts
# ---------------------------------------------------------------------------


class TestListContracts:
    async def test_returns_paginated(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.get("/api/v1/contracts", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert "pagination" in body
        assert isinstance(body["data"], list)

    async def test_filter_by_status(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _create_client(client, headers)
        did = await _create_deal(client, headers, cid)
        pid = await _create_accepted_proposal(client, headers, did)
        await _create_contract(client, headers, did, pid, cid)

        resp = await client.get("/api/v1/contracts", params={"status": "draft"}, headers=headers)
        assert resp.status_code == 200
        for c in resp.json()["data"]:
            assert c["status"] == "draft"

    async def test_filter_by_deal_id(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _create_client(client, headers)
        did = await _create_deal(client, headers, cid)
        pid = await _create_accepted_proposal(client, headers, did)
        await _create_contract(client, headers, did, pid, cid)

        resp = await client.get("/api/v1/contracts", params={"deal_id": did}, headers=headers)
        assert resp.status_code == 200
        for c in resp.json()["data"]:
            assert c["deal_id"] == did

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/contracts")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /contracts
# ---------------------------------------------------------------------------


class TestCreateContract:
    async def test_creates_from_accepted_proposal(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _create_client(client, headers)
        did = await _create_deal(client, headers, cid)
        pid = await _create_accepted_proposal(client, headers, did)

        resp = await client.post(
            "/api/v1/contracts",
            json={
                "deal_id": did,
                "proposal_id": pid,
                "client_id": cid,
                "content": {"title": "Service Agreement"},
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["status"] == "draft"
        assert body["data"]["client_snapshot"]["name"] == "Acme Corp"

    async def test_rejects_non_accepted_proposal(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _create_client(client, headers)
        did = await _create_deal(client, headers, cid)

        # Proposal stays draft
        resp_p = await client.post(
            "/api/v1/proposals",
            json={"deal_id": did, "content": {}},
            headers=headers,
        )
        pid = resp_p.json()["data"]["id"]

        resp = await client.post(
            "/api/v1/contracts",
            json={"deal_id": did, "proposal_id": pid, "client_id": cid, "content": {}},
            headers=headers,
        )
        assert resp.status_code == 409, resp.text

    async def test_missing_fields_returns_422(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.post("/api/v1/contracts", json={}, headers=headers)
        assert resp.status_code == 422

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/contracts", json={})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /contracts/:id/status
# ---------------------------------------------------------------------------


class TestTransitionContractStatus:
    async def test_draft_to_pending_signatures(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _create_client(client, headers)
        did = await _create_deal(client, headers, cid)
        pid = await _create_accepted_proposal(client, headers, did)
        contract_id = await _create_contract(client, headers, did, pid, cid)

        resp = await client.patch(
            f"/api/v1/contracts/{contract_id}/status",
            json={"status": "pending_signatures"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "pending_signatures"

    async def test_invalid_transition_returns_409(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _create_client(client, headers)
        did = await _create_deal(client, headers, cid)
        pid = await _create_accepted_proposal(client, headers, did)
        contract_id = await _create_contract(client, headers, did, pid, cid)

        resp = await client.patch(
            f"/api/v1/contracts/{contract_id}/status",
            json={"status": "completed"},  # draft → completed is invalid
            headers=headers,
        )
        assert resp.status_code == 409, resp.text

    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.patch(
            f"/api/v1/contracts/{uuid.uuid4()}/status",
            json={"status": "pending_signatures"},
            headers=headers,
        )
        assert resp.status_code == 404, resp.text

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.patch(
            f"/api/v1/contracts/{uuid.uuid4()}/status",
            json={"status": "pending_signatures"},
        )
        assert resp.status_code == 401

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        cid = await _create_client(client, headers_a)
        did = await _create_deal(client, headers_a, cid)
        pid = await _create_accepted_proposal(client, headers_a, did)
        contract_id = await _create_contract(client, headers_a, did, pid, cid)

        resp = await client.patch(
            f"/api/v1/contracts/{contract_id}/status",
            json={"status": "pending_signatures"},
            headers=headers_b,
        )
        assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# GET /contracts/:id/export
# ---------------------------------------------------------------------------


class TestExportContractPdf:
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/contracts/{uuid.uuid4()}/export")
        assert resp.status_code == 401

    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.get(f"/api/v1/contracts/{uuid.uuid4()}/export", headers=headers)
        assert resp.status_code == 404

    async def test_free_plan_returns_402(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _create_client(client, headers)
        did = await _create_deal(client, headers, cid)
        pid = await _create_accepted_proposal(client, headers, did)
        contract_id = await _create_contract(client, headers, did, pid, cid)

        # Default plan has can_export_pdf=False → expect 402
        resp = await client.get(f"/api/v1/contracts/{contract_id}/export", headers=headers)
        assert resp.status_code == 402, resp.text

    async def test_with_pdf_entitlement_returns_pending(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _create_client(client, headers)
        did = await _create_deal(client, headers, cid)
        pid = await _create_accepted_proposal(client, headers, did)
        contract_id = await _create_contract(client, headers, did, pid, cid)

        mock_task = MagicMock(id="test-task-id")
        with (
            patch("src.workers.pdf_jobs.tasks.render_contract_pdf") as mock_fn,
            patch(
                "src.modules.contracts.application.service.ContractsService.export_pdf",
                return_value={"status": "pending", "task_id": "test-task-id", "download_url": None},
            ),
        ):
            mock_fn.delay.return_value = mock_task
            resp = await client.get(f"/api/v1/contracts/{contract_id}/export", headers=headers)

        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "pending"


# ---------------------------------------------------------------------------
# DELETE /contracts/:id
# ---------------------------------------------------------------------------


class TestDeleteContract:
    async def test_deletes_draft_returns_200(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _create_client(client, headers)
        did = await _create_deal(client, headers, cid)
        pid = await _create_accepted_proposal(client, headers, did)
        contract_id = await _create_contract(client, headers, did, pid, cid)

        resp = await client.delete(f"/api/v1/contracts/{contract_id}", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["detail"] == "Contract deleted"

    async def test_cannot_delete_active_returns_409(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _create_client(client, headers)
        did = await _create_deal(client, headers, cid)
        pid = await _create_accepted_proposal(client, headers, did)
        contract_id = await _create_contract(client, headers, did, pid, cid)

        await client.patch(
            f"/api/v1/contracts/{contract_id}/status",
            json={"status": "pending_signatures"},
            headers=headers,
        )
        await client.patch(
            f"/api/v1/contracts/{contract_id}/status",
            json={"status": "active"},
            headers=headers,
        )
        resp = await client.delete(f"/api/v1/contracts/{contract_id}", headers=headers)
        assert resp.status_code == 409, resp.text

    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.delete(f"/api/v1/contracts/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.delete(f"/api/v1/contracts/{uuid.uuid4()}")
        assert resp.status_code == 401

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        cid = await _create_client(client, headers_a)
        did = await _create_deal(client, headers_a, cid)
        pid = await _create_accepted_proposal(client, headers_a, did)
        contract_id = await _create_contract(client, headers_a, did, pid, cid)

        resp = await client.delete(f"/api/v1/contracts/{contract_id}", headers=headers_b)
        assert resp.status_code == 404
