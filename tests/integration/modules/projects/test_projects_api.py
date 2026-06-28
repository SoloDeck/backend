"""Integration tests for the projects API (real PostgreSQL, rolled back per test)."""

import uuid
from typing import Any

from httpx import AsyncClient

from tests.integration.modules.clients.test_clients_api import _auth_headers


def _project_payload(**overrides: object) -> dict[str, Any]:
    return {"name": f"Project {uuid.uuid4().hex[:6]}", **overrides}


async def _create_project(
    http: AsyncClient, headers: dict[str, str], **overrides: object
) -> dict[str, Any]:
    resp = await http.post("/api/v1/projects", json=_project_payload(**overrides), headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]  # type: ignore[no-any-return]


class TestCreateProject:
    async def test_create_project_201(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        resp = await client.post(
            "/api/v1/projects",
            json={"name": "Landing page", "description": "Một dự án mẫu"},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["name"] == "Landing page"
        assert data["status"] == "planning"
        assert data["task_count"] == 0
        assert data["done_count"] == 0

    async def test_create_project_requires_auth_401(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/projects", json={"name": "x"})
        assert resp.status_code == 401

    async def test_create_project_missing_name_422(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        resp = await client.post("/api/v1/projects", json={}, headers=headers)
        assert resp.status_code == 422


class TestListProjects:
    async def test_list_projects_200(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        await _create_project(client, headers)
        await _create_project(client, headers)

        resp = await client.get("/api/v1/projects", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["data"]) == 2
        assert body["pagination"]["total"] == 2

    async def test_list_projects_filter_by_status(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        proj = await _create_project(client, headers)
        await client.put(
            f"/api/v1/projects/{proj['id']}", json={"status": "active"}, headers=headers
        )
        await _create_project(client, headers)  # stays planning

        resp = await client.get("/api/v1/projects?status=active", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["status"] == "active"


class TestGetProject:
    async def test_get_project_200(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        proj = await _create_project(client, headers)

        resp = await client.get(f"/api/v1/projects/{proj['id']}", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["id"] == proj["id"]

    async def test_get_project_wrong_owner_404(self, client: AsyncClient) -> None:
        owner_a = await _auth_headers(client)
        proj = await _create_project(client, owner_a)
        owner_b = await _auth_headers(client)

        resp = await client.get(f"/api/v1/projects/{proj['id']}", headers=owner_b)
        assert resp.status_code == 404


class TestUpdateProject:
    async def test_update_project_200(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        proj = await _create_project(client, headers)

        resp = await client.put(
            f"/api/v1/projects/{proj['id']}",
            json={"name": "Renamed", "status": "on_hold"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["name"] == "Renamed"
        assert data["status"] == "on_hold"


class TestDeleteProject:
    async def test_delete_project_204(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        proj = await _create_project(client, headers)

        resp = await client.delete(f"/api/v1/projects/{proj['id']}", headers=headers)
        assert resp.status_code == 204

        # gone afterwards
        follow = await client.get(f"/api/v1/projects/{proj['id']}", headers=headers)
        assert follow.status_code == 404
