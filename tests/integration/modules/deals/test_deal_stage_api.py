"""Integration coverage for deal stage transition API schema."""

import uuid

from httpx import AsyncClient

from tests.integration.modules.clients.test_clients_api import _auth_headers, _create_client


async def test_stage_transition_accepts_target_stage_field(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    client_obj = await _create_client(client, headers)
    create_resp = await client.post(
        "/api/v1/deals",
        json={"client_id": client_obj["id"], "title": f"Deal {uuid.uuid4().hex[:6]}"},
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    deal = create_resp.json()["data"]

    resp = await client.post(
        f"/api/v1/deals/{deal['id']}/stage",
        json={"target_stage": "qualified"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["stage"] == "qualified"
