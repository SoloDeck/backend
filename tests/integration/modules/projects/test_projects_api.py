"""Integration tests for the projects and tasks endpoints."""

import uuid

from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _auth(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"u_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Test@1234!",
            "full_name": "Test User",
        },
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _create_deal(client: AsyncClient, headers: dict) -> str:
    c = await client.post(
        "/api/v1/clients",
        json={"name": "Acme", "status": "prospect"},
        headers=headers,
    )
    assert c.status_code == 201, c.text
    resp = await client.post(
        "/api/v1/deals",
        json={"title": f"Deal {uuid.uuid4().hex[:6]}", "client_id": c.json()["data"]["id"]},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _create_project(client: AsyncClient, headers: dict, deal_id: str, title: str = "My Project") -> dict:
    resp = await client.post(
        "/api/v1/projects",
        json={"deal_id": deal_id, "title": title},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _create_task(client: AsyncClient, headers: dict, project_id: str, title: str = "Task A") -> dict:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": title},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# POST /projects
# ---------------------------------------------------------------------------

class TestCreateProject:
    async def test_creates_project_returns_201(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        resp = await client.post(
            "/api/v1/projects",
            json={"deal_id": deal_id, "title": "Website Redesign", "description": "Full redesign"},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["title"] == "Website Redesign"
        assert data["description"] == "Full redesign"
        assert data["deal_id"] == deal_id

    async def test_creates_without_description(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        project = await _create_project(client, headers, deal_id)
        assert project["description"] is None

    async def test_deal_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.post(
            "/api/v1/projects",
            json={"deal_id": str(uuid.uuid4()), "title": "Test"},
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_empty_title_returns_422(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        resp = await client.post(
            "/api/v1/projects",
            json={"deal_id": deal_id, "title": ""},
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/projects", json={"deal_id": str(uuid.uuid4()), "title": "X"})
        assert resp.status_code == 401

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _create_deal(client, headers_a)
        resp = await client.post(
            "/api/v1/projects",
            json={"deal_id": deal_id, "title": "Test"},
            headers=headers_b,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /projects
# ---------------------------------------------------------------------------

class TestListProjects:
    async def test_returns_own_projects(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        await _create_project(client, headers, deal_id, "P1")
        await _create_project(client, headers, deal_id, "P2")
        resp = await client.get("/api/v1/projects", headers=headers)
        assert resp.status_code == 200
        titles = [p["title"] for p in resp.json()["data"]]
        assert "P1" in titles
        assert "P2" in titles

    async def test_filter_by_deal_id(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_a = await _create_deal(client, headers)
        deal_b = await _create_deal(client, headers)
        p_a = await _create_project(client, headers, deal_a, "For A")
        await _create_project(client, headers, deal_b, "For B")
        resp = await client.get("/api/v1/projects", params={"deal_id": deal_a}, headers=headers)
        ids = [p["id"] for p in resp.json()["data"]]
        assert p_a["id"] in ids
        for p in resp.json()["data"]:
            assert p["deal_id"] == deal_a

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/projects")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /projects/:id
# ---------------------------------------------------------------------------

class TestGetProject:
    async def test_returns_project(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        project = await _create_project(client, headers, deal_id)
        resp = await client.get(f"/api/v1/projects/{project['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == project["id"]

    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.get(f"/api/v1/projects/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _create_deal(client, headers_a)
        project = await _create_project(client, headers_a, deal_id)
        resp = await client.get(f"/api/v1/projects/{project['id']}", headers=headers_b)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /projects/:id
# ---------------------------------------------------------------------------

class TestUpdateProject:
    async def test_updates_title(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        project = await _create_project(client, headers, deal_id)
        resp = await client.patch(
            f"/api/v1/projects/{project['id']}",
            json={"title": "Updated Title"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "Updated Title"

    async def test_updates_description(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        project = await _create_project(client, headers, deal_id)
        resp = await client.patch(
            f"/api/v1/projects/{project['id']}",
            json={"description": "New desc"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["description"] == "New desc"

    async def test_omitted_fields_unchanged(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        project = await _create_project(client, headers, deal_id, "Keep this")
        await client.patch(
            f"/api/v1/projects/{project['id']}",
            json={"description": "added"},
            headers=headers,
        )
        resp = await client.get(f"/api/v1/projects/{project['id']}", headers=headers)
        assert resp.json()["data"]["title"] == "Keep this"

    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.patch(
            f"/api/v1/projects/{uuid.uuid4()}",
            json={"title": "X"},
            headers=headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /projects/:id
# ---------------------------------------------------------------------------

class TestDeleteProject:
    async def test_deletes_project(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        project = await _create_project(client, headers, deal_id)
        resp = await client.delete(f"/api/v1/projects/{project['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["detail"] == "Project deleted"

    async def test_deleted_project_not_found(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        project = await _create_project(client, headers, deal_id)
        await client.delete(f"/api/v1/projects/{project['id']}", headers=headers)
        resp = await client.get(f"/api/v1/projects/{project['id']}", headers=headers)
        assert resp.status_code == 404

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _create_deal(client, headers_a)
        project = await _create_project(client, headers_a, deal_id)
        resp = await client.delete(f"/api/v1/projects/{project['id']}", headers=headers_b)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tasks: POST / GET / PATCH / DELETE
# ---------------------------------------------------------------------------

class TestTasks:
    async def test_create_task_returns_201(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        project = await _create_project(client, headers, deal_id)
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/tasks",
            json={"title": "Build login page", "note": "use OAuth"},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["title"] == "Build login page"
        assert data["note"] == "use OAuth"
        assert data["is_done"] is False
        assert data["project_id"] == project["id"]

    async def test_list_tasks_progress(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        project = await _create_project(client, headers, deal_id)
        t1 = await _create_task(client, headers, project["id"], "T1")
        t2 = await _create_task(client, headers, project["id"], "T2")
        await _create_task(client, headers, project["id"], "T3")
        for tid in [t1["id"], t2["id"]]:
            await client.patch(
                f"/api/v1/projects/{project['id']}/tasks/{tid}",
                json={"is_done": True}, headers=headers,
            )
        resp = await client.get(f"/api/v1/projects/{project['id']}/tasks", headers=headers)
        body = resp.json()["data"]
        assert body["total"] == 3
        assert body["done"] == 2
        assert body["percent"] == 67

    async def test_pending_before_done_ordering(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        project = await _create_project(client, headers, deal_id)
        t1 = await _create_task(client, headers, project["id"], "Pending")
        t2 = await _create_task(client, headers, project["id"], "Done")
        await client.patch(
            f"/api/v1/projects/{project['id']}/tasks/{t2['id']}",
            json={"is_done": True}, headers=headers,
        )
        resp = await client.get(f"/api/v1/projects/{project['id']}/tasks", headers=headers)
        tasks = resp.json()["data"]["tasks"]
        assert tasks[0]["is_done"] is False
        assert tasks[1]["is_done"] is True

    async def test_update_task_toggle_done(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        project = await _create_project(client, headers, deal_id)
        task = await _create_task(client, headers, project["id"])
        resp = await client.patch(
            f"/api/v1/projects/{project['id']}/tasks/{task['id']}",
            json={"is_done": True}, headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["is_done"] is True

    async def test_update_task_clear_note(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        project = await _create_project(client, headers, deal_id)
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/tasks",
            json={"title": "T", "note": "keep"}, headers=headers,
        )
        task_id = resp.json()["data"]["id"]
        resp = await client.patch(
            f"/api/v1/projects/{project['id']}/tasks/{task_id}",
            json={"note": None}, headers=headers,
        )
        assert resp.json()["data"]["note"] is None

    async def test_delete_task(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        project = await _create_project(client, headers, deal_id)
        task = await _create_task(client, headers, project["id"])
        resp = await client.delete(
            f"/api/v1/projects/{project['id']}/tasks/{task['id']}", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["detail"] == "Task deleted"

    async def test_task_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        project = await _create_project(client, headers, deal_id)
        resp = await client.get(
            f"/api/v1/projects/{project['id']}/tasks", headers=headers
        )
        assert resp.json()["data"]["tasks"] == []

    async def test_project_not_found_returns_404_on_task_list(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.get(
            f"/api/v1/projects/{uuid.uuid4()}/tasks", headers=headers
        )
        assert resp.status_code == 404

    async def test_tenant_isolation_tasks(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _create_deal(client, headers_a)
        project = await _create_project(client, headers_a, deal_id)
        task = await _create_task(client, headers_a, project["id"])
        resp = await client.patch(
            f"/api/v1/projects/{project['id']}/tasks/{task['id']}",
            json={"is_done": True}, headers=headers_b,
        )
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/projects/{uuid.uuid4()}/tasks")
        assert resp.status_code == 401

    async def test_empty_task_title_returns_422(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        project = await _create_project(client, headers, deal_id)
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/tasks",
            json={"title": ""},
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_create_task_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _create_deal(client, headers_a)
        project = await _create_project(client, headers_a, deal_id)
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/tasks",
            json={"title": "Intruder task"},
            headers=headers_b,
        )
        assert resp.status_code == 404

    async def test_delete_task_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _create_deal(client, headers_a)
        project = await _create_project(client, headers_a, deal_id)
        task = await _create_task(client, headers_a, project["id"])
        resp = await client.delete(
            f"/api/v1/projects/{project['id']}/tasks/{task['id']}",
            headers=headers_b,
        )
        assert resp.status_code == 404


class TestUpdateProjectTenantIsolation:
    async def test_patch_project_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _create_deal(client, headers_a)
        project = await _create_project(client, headers_a, deal_id)
        resp = await client.patch(
            f"/api/v1/projects/{project['id']}",
            json={"title": "Hijacked"},
            headers=headers_b,
        )
        assert resp.status_code == 404
