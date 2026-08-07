"""Integration tests for /contracts/{id}/milestones CRUD endpoints."""

import uuid

from httpx import AsyncClient

from tests.integration.modules.contracts.test_contracts_api import (
    _auth,
    _create_accepted_proposal,
    _create_client,
    _create_contract,
    _create_deal,
)


async def _setup_draft_contract(client: AsyncClient) -> tuple[dict, str]:
    """Returns (headers, contract_id) for a fresh draft contract."""
    headers = await _auth(client)
    cid = await _create_client(client, headers)
    did = await _create_deal(client, headers, cid)
    pid = await _create_accepted_proposal(client, headers, did)
    contract_id = await _create_contract(client, headers, did, pid, cid)
    return headers, contract_id


class TestListMilestones:
    async def test_returns_empty_list_for_new_contract(self, client: AsyncClient) -> None:
        headers, contract_id = await _setup_draft_contract(client)
        resp = await client.get(f"/api/v1/contracts/{contract_id}/milestones", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"] == []

    async def test_other_users_contract_returns_404(self, client: AsyncClient) -> None:
        _, contract_id = await _setup_draft_contract(client)
        other_headers = await _auth(client)
        resp = await client.get(
            f"/api/v1/contracts/{contract_id}/milestones", headers=other_headers
        )
        assert resp.status_code == 404


class TestAddMilestone:
    async def test_add_milestone_returns_201(self, client: AsyncClient) -> None:
        headers, contract_id = await _setup_draft_contract(client)
        resp = await client.post(
            f"/api/v1/contracts/{contract_id}/milestones",
            json={"description": "Upfront deposit", "amount": "2500000", "sort_order": 1},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()["data"]
        assert body["description"] == "Upfront deposit"
        assert body["amount"] == "2500000.00"
        assert body["sort_order"] == 1

    async def test_negative_amount_returns_422(self, client: AsyncClient) -> None:
        headers, contract_id = await _setup_draft_contract(client)
        resp = await client.post(
            f"/api/v1/contracts/{contract_id}/milestones",
            json={"description": "Bad", "amount": "-100"},
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_non_draft_contract_returns_409(self, client: AsyncClient) -> None:
        headers, contract_id = await _setup_draft_contract(client)
        await client.post(f"/api/v1/contracts/{contract_id}/send", headers=headers)

        resp = await client.post(
            f"/api/v1/contracts/{contract_id}/milestones",
            json={"description": "Too late", "amount": "1000000"},
            headers=headers,
        )
        assert resp.status_code == 409

    async def test_nonexistent_contract_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.post(
            f"/api/v1/contracts/{uuid.uuid4()}/milestones",
            json={"description": "x", "amount": "100"},
            headers=headers,
        )
        assert resp.status_code == 404


class TestUpdateMilestone:
    async def test_update_amount_returns_200(self, client: AsyncClient) -> None:
        headers, contract_id = await _setup_draft_contract(client)
        create_resp = await client.post(
            f"/api/v1/contracts/{contract_id}/milestones",
            json={"description": "Deposit", "amount": "1000000"},
            headers=headers,
        )
        milestone_id = create_resp.json()["data"]["id"]

        resp = await client.patch(
            f"/api/v1/contracts/{contract_id}/milestones/{milestone_id}",
            json={"amount": "1500000"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["amount"] == "1500000.00"
        assert resp.json()["data"]["description"] == "Deposit"

    async def test_nonexistent_milestone_returns_404(self, client: AsyncClient) -> None:
        headers, contract_id = await _setup_draft_contract(client)
        resp = await client.patch(
            f"/api/v1/contracts/{contract_id}/milestones/{uuid.uuid4()}",
            json={"amount": "100"},
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_non_draft_contract_returns_409(self, client: AsyncClient) -> None:
        headers, contract_id = await _setup_draft_contract(client)
        create_resp = await client.post(
            f"/api/v1/contracts/{contract_id}/milestones",
            json={"description": "Deposit", "amount": "1000000"},
            headers=headers,
        )
        milestone_id = create_resp.json()["data"]["id"]
        await client.post(f"/api/v1/contracts/{contract_id}/send", headers=headers)

        resp = await client.patch(
            f"/api/v1/contracts/{contract_id}/milestones/{milestone_id}",
            json={"amount": "999"},
            headers=headers,
        )
        assert resp.status_code == 409


class TestDeleteMilestone:
    async def test_delete_returns_204(self, client: AsyncClient) -> None:
        headers, contract_id = await _setup_draft_contract(client)
        create_resp = await client.post(
            f"/api/v1/contracts/{contract_id}/milestones",
            json={"description": "Deposit", "amount": "1000000"},
            headers=headers,
        )
        milestone_id = create_resp.json()["data"]["id"]

        resp = await client.delete(
            f"/api/v1/contracts/{contract_id}/milestones/{milestone_id}", headers=headers
        )
        assert resp.status_code == 204

        list_resp = await client.get(
            f"/api/v1/contracts/{contract_id}/milestones", headers=headers
        )
        assert list_resp.json()["data"] == []

    async def test_non_draft_contract_returns_409(self, client: AsyncClient) -> None:
        headers, contract_id = await _setup_draft_contract(client)
        create_resp = await client.post(
            f"/api/v1/contracts/{contract_id}/milestones",
            json={"description": "Deposit", "amount": "1000000"},
            headers=headers,
        )
        milestone_id = create_resp.json()["data"]["id"]
        await client.post(f"/api/v1/contracts/{contract_id}/send", headers=headers)

        resp = await client.delete(
            f"/api/v1/contracts/{contract_id}/milestones/{milestone_id}", headers=headers
        )
        assert resp.status_code == 409
