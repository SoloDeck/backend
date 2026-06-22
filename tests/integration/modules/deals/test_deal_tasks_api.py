"""Integration tests for deal task (todo list) endpoints."""

import uuid

from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _auth(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"user_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Test@1234!",
            "full_name": "Test User",
        },
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _create_deal(client: AsyncClient, headers: dict) -> str:
    c = await client.post(
        "/api/v1/clients",
        json={"name": "Acme Corp", "status": "prospect"},
        headers=headers,
    )
    assert c.status_code == 201, c.text
    client_id = c.json()["data"]["id"]

    d = await client.post(
        "/api/v1/deals",
        json={"title": f"Deal {uuid.uuid4().hex[:6]}", "client_id": client_id},
        headers=headers,
    )
    assert d.status_code == 201, d.text
    return d.json()["data"]["id"]


async def _create_task(
    client: AsyncClient, headers: dict, deal_id: str, title: str = "Task A", note: str | None = None
) -> dict:
    body: dict = {"title": title}
    if note is not None:
        body["note"] = note
    resp = await client.post(f"/api/v1/deals/{deal_id}/tasks", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# POST /deals/:deal_id/tasks
# ---------------------------------------------------------------------------

class TestCreateTask:
    async def test_creates_task_returns_201(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)

        resp = await client.post(
            f"/api/v1/deals/{deal_id}/tasks",
            json={"title": "bàn giao 40%", "note": "send by Friday"},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["title"] == "bàn giao 40%"
        assert data["note"] == "send by Friday"
        assert data["is_done"] is False
        assert data["deal_id"] == deal_id

    async def test_creates_task_without_note(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        task = await _create_task(client, headers, deal_id)
        assert task["note"] is None

    async def test_empty_title_returns_422(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        resp = await client.post(
            f"/api/v1/deals/{deal_id}/tasks", json={"title": ""}, headers=headers
        )
        assert resp.status_code == 422

    async def test_missing_title_returns_422(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        resp = await client.post(
            f"/api/v1/deals/{deal_id}/tasks", json={}, headers=headers
        )
        assert resp.status_code == 422

    async def test_deal_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.post(
            f"/api/v1/deals/{uuid.uuid4()}/tasks",
            json={"title": "Task"},
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"/api/v1/deals/{uuid.uuid4()}/tasks", json={"title": "Task"}
        )
        assert resp.status_code == 401

    async def test_tenant_isolation_cannot_create_on_other_users_deal(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _create_deal(client, headers_a)
        resp = await client.post(
            f"/api/v1/deals/{deal_id}/tasks",
            json={"title": "Task"},
            headers=headers_b,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /deals/:deal_id/tasks
# ---------------------------------------------------------------------------

class TestListTasks:
    async def test_empty_list_returns_zero_progress(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        resp = await client.get(f"/api/v1/deals/{deal_id}/tasks", headers=headers)
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["tasks"] == []
        assert body["total"] == 0
        assert body["done"] == 0
        assert body["percent"] == 0

    async def test_returns_all_tasks_with_progress(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)

        t1 = await _create_task(client, headers, deal_id, "Task 1")
        t2 = await _create_task(client, headers, deal_id, "Task 2")
        t3 = await _create_task(client, headers, deal_id, "Task 3")

        # Mark t1 and t2 done
        await client.patch(
            f"/api/v1/deals/{deal_id}/tasks/{t1['id']}",
            json={"is_done": True}, headers=headers,
        )
        await client.patch(
            f"/api/v1/deals/{deal_id}/tasks/{t2['id']}",
            json={"is_done": True}, headers=headers,
        )

        resp = await client.get(f"/api/v1/deals/{deal_id}/tasks", headers=headers)
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["total"] == 3
        assert body["done"] == 2
        assert body["percent"] == 67

    async def test_pending_tasks_before_done_tasks(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)

        t1 = await _create_task(client, headers, deal_id, "Pending")
        t2 = await _create_task(client, headers, deal_id, "Done")
        await client.patch(
            f"/api/v1/deals/{deal_id}/tasks/{t2['id']}",
            json={"is_done": True}, headers=headers,
        )

        resp = await client.get(f"/api/v1/deals/{deal_id}/tasks", headers=headers)
        tasks = resp.json()["data"]["tasks"]
        assert tasks[0]["is_done"] is False
        assert tasks[1]["is_done"] is True

    async def test_deal_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.get(f"/api/v1/deals/{uuid.uuid4()}/tasks", headers=headers)
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/deals/{uuid.uuid4()}/tasks")
        assert resp.status_code == 401

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _create_deal(client, headers_a)
        await _create_task(client, headers_a, deal_id, "Secret task")

        resp = await client.get(f"/api/v1/deals/{deal_id}/tasks", headers=headers_b)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /deals/:deal_id/tasks/:task_id
# ---------------------------------------------------------------------------

class TestUpdateTask:
    async def test_toggle_is_done(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        task = await _create_task(client, headers, deal_id, "Toggle me")

        resp = await client.patch(
            f"/api/v1/deals/{deal_id}/tasks/{task['id']}",
            json={"is_done": True},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["is_done"] is True

    async def test_update_title(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        task = await _create_task(client, headers, deal_id, "Old title")

        resp = await client.patch(
            f"/api/v1/deals/{deal_id}/tasks/{task['id']}",
            json={"title": "New title"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "New title"

    async def test_update_note(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        task = await _create_task(client, headers, deal_id)

        resp = await client.patch(
            f"/api/v1/deals/{deal_id}/tasks/{task['id']}",
            json={"note": "added a note"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["note"] == "added a note"

    async def test_clear_note_with_null(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        task = await _create_task(client, headers, deal_id, note="existing note")

        resp = await client.patch(
            f"/api/v1/deals/{deal_id}/tasks/{task['id']}",
            json={"note": None},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["note"] is None

    async def test_omitted_fields_unchanged(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        task = await _create_task(client, headers, deal_id, "Stay same", note="keep this")

        resp = await client.patch(
            f"/api/v1/deals/{deal_id}/tasks/{task['id']}",
            json={"is_done": True},
            headers=headers,
        )
        data = resp.json()["data"]
        assert data["title"] == "Stay same"
        assert data["note"] == "keep this"
        assert data["is_done"] is True

    async def test_empty_title_returns_422(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        task = await _create_task(client, headers, deal_id)
        resp = await client.patch(
            f"/api/v1/deals/{deal_id}/tasks/{task['id']}",
            json={"title": ""},
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_task_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        resp = await client.patch(
            f"/api/v1/deals/{deal_id}/tasks/{uuid.uuid4()}",
            json={"is_done": True},
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _create_deal(client, headers_a)
        task = await _create_task(client, headers_a, deal_id)

        resp = await client.patch(
            f"/api/v1/deals/{deal_id}/tasks/{task['id']}",
            json={"is_done": True},
            headers=headers_b,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /deals/:deal_id/tasks/:task_id
# ---------------------------------------------------------------------------

class TestDeleteTask:
    async def test_deletes_task_returns_200(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        task = await _create_task(client, headers, deal_id)

        resp = await client.delete(
            f"/api/v1/deals/{deal_id}/tasks/{task['id']}", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["detail"] == "Task deleted"

    async def test_deleted_task_gone_from_list(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        task = await _create_task(client, headers, deal_id)

        await client.delete(
            f"/api/v1/deals/{deal_id}/tasks/{task['id']}", headers=headers
        )
        resp = await client.get(f"/api/v1/deals/{deal_id}/tasks", headers=headers)
        ids = [t["id"] for t in resp.json()["data"]["tasks"]]
        assert task["id"] not in ids

    async def test_task_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers)
        resp = await client.delete(
            f"/api/v1/deals/{deal_id}/tasks/{uuid.uuid4()}", headers=headers
        )
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.delete(
            f"/api/v1/deals/{uuid.uuid4()}/tasks/{uuid.uuid4()}"
        )
        assert resp.status_code == 401

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _create_deal(client, headers_a)
        task = await _create_task(client, headers_a, deal_id)

        resp = await client.delete(
            f"/api/v1/deals/{deal_id}/tasks/{task['id']}", headers=headers_b
        )
        assert resp.status_code == 404
