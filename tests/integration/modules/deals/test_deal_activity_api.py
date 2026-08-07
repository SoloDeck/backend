"""Integration tests for GET /deals/{id}/activity and POST /deals/{id}/notes."""

import uuid

from httpx import AsyncClient

from tests.integration.modules.clients.test_clients_api import _auth_headers, _create_client


async def _create_deal(client: AsyncClient, headers: dict, client_id: str) -> dict:
    resp = await client.post(
        "/api/v1/deals",
        json={"client_id": client_id, "title": f"Deal {uuid.uuid4().hex[:6]}"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


class TestListDealActivity:
    async def test_stage_transition_is_logged(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        c = await _create_client(client, headers)
        deal = await _create_deal(client, headers, c["id"])

        await client.post(
            f"/api/v1/deals/{deal['id']}/stage",
            json={"target_stage": "qualified"},
            headers=headers,
        )

        resp = await client.get(f"/api/v1/deals/{deal['id']}/activity", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        entries = body["data"]
        assert body["pagination"]["total"] == 1
        assert entries[0]["entry_type"] == "stage_change"
        assert entries[0]["previous_stage"] == "new_lead"
        assert entries[0]["new_stage"] == "qualified"

    async def test_filter_by_entry_type(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        c = await _create_client(client, headers)
        deal = await _create_deal(client, headers, c["id"])

        await client.post(
            f"/api/v1/deals/{deal['id']}/stage",
            json={"target_stage": "qualified"},
            headers=headers,
        )
        await client.post(
            f"/api/v1/deals/{deal['id']}/notes",
            json={"description": "Left a voicemail"},
            headers=headers,
        )

        resp = await client.get(
            f"/api/v1/deals/{deal['id']}/activity?entry_type=note_added", headers=headers
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["pagination"]["total"] == 1
        assert all(e["entry_type"] == "note_added" for e in body["data"])

    async def test_invalid_entry_type_returns_422(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        c = await _create_client(client, headers)
        deal = await _create_deal(client, headers, c["id"])

        resp = await client.get(
            f"/api/v1/deals/{deal['id']}/activity?entry_type=not_a_real_type", headers=headers
        )
        assert resp.status_code == 422, resp.text

    async def test_other_users_deal_returns_404(self, client: AsyncClient) -> None:
        headers_a = await _auth_headers(client)
        headers_b = await _auth_headers(client)
        c = await _create_client(client, headers_a)
        deal = await _create_deal(client, headers_a, c["id"])

        resp = await client.get(f"/api/v1/deals/{deal['id']}/activity", headers=headers_b)
        assert resp.status_code == 404, resp.text

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/deals/{uuid.uuid4()}/activity")
        assert resp.status_code == 401


class TestAddDealNote:
    async def test_add_note_returns_201(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        c = await _create_client(client, headers)
        deal = await _create_deal(client, headers, c["id"])

        resp = await client.post(
            f"/api/v1/deals/{deal['id']}/notes",
            json={"description": "Client wants a revised quote"},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()["data"]
        assert body["entry_type"] == "note_added"
        assert body["description"] == "Client wants a revised quote"

    async def test_empty_description_returns_422(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        c = await _create_client(client, headers)
        deal = await _create_deal(client, headers, c["id"])

        resp = await client.post(
            f"/api/v1/deals/{deal['id']}/notes",
            json={"description": ""},
            headers=headers,
        )
        assert resp.status_code == 422, resp.text

    async def test_nonexistent_deal_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        resp = await client.post(
            f"/api/v1/deals/{uuid.uuid4()}/notes",
            json={"description": "x"},
            headers=headers,
        )
        assert resp.status_code == 404, resp.text

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"/api/v1/deals/{uuid.uuid4()}/notes",
            json={"description": "x"},
        )
        assert resp.status_code == 401
