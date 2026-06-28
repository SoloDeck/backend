"""Integration tests for the polymorphic tasks API (real PostgreSQL)."""

import uuid
from typing import Any

from httpx import AsyncClient

from tests.integration.modules.clients.test_clients_api import _auth_headers, _create_client


async def _create_project(http: AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    resp = await http.post(
        "/api/v1/projects", json={"name": f"Project {uuid.uuid4().hex[:6]}"}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]  # type: ignore[no-any-return]


async def _create_deal(http: AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    client_obj = await _create_client(http, headers)
    resp = await http.post(
        "/api/v1/deals",
        json={"client_id": client_obj["id"], "title": f"Deal {uuid.uuid4().hex[:6]}"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]  # type: ignore[no-any-return]


async def _create_task_under_project(
    http: AsyncClient, headers: dict[str, str], project_id: str
) -> dict[str, Any]:
    resp = await http.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": f"Task {uuid.uuid4().hex[:6]}"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]  # type: ignore[no-any-return]


class TestCreateTask:
    async def test_create_task_under_project_201(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        project = await _create_project(client, headers)

        resp = await client.post(
            f"/api/v1/projects/{project['id']}/tasks",
            json={"title": "Thiết kế giao diện", "priority": "high"},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["entity_type"] == "project"
        assert data["entity_id"] == project["id"]
        assert data["priority"] == "high"
        assert data["status"] == "todo"
        assert data["checklist_items"] == []

    async def test_create_task_under_deal_201(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        deal = await _create_deal(client, headers)

        resp = await client.post(
            f"/api/v1/deals/{deal['id']}/tasks",
            json={"title": "Gọi điện khách hàng"},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["entity_type"] == "deal"
        assert data["entity_id"] == deal["id"]
        assert data["priority"] == "medium"  # default

    async def test_create_task_unknown_project_404(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        resp = await client.post(
            f"/api/v1/projects/{uuid.uuid4()}/tasks",
            json={"title": "x"},
            headers=headers,
        )
        assert resp.status_code == 404


class TestListTasks:
    async def test_list_tasks_under_project_200(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        project = await _create_project(client, headers)
        await _create_task_under_project(client, headers, project["id"])
        await _create_task_under_project(client, headers, project["id"])

        resp = await client.get(f"/api/v1/projects/{project['id']}/tasks", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["data"]) == 2
        assert body["pagination"]["total"] == 2

    async def test_list_tasks_isolated_per_entity(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        project_a = await _create_project(client, headers)
        project_b = await _create_project(client, headers)
        await _create_task_under_project(client, headers, project_a["id"])

        resp = await client.get(f"/api/v1/projects/{project_b['id']}/tasks", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"] == []


class TestTaskDetail:
    async def test_get_task_200(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        project = await _create_project(client, headers)
        task = await _create_task_under_project(client, headers, project["id"])

        resp = await client.get(f"/api/v1/tasks/{task['id']}", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["id"] == task["id"]

    async def test_get_task_wrong_owner_404(self, client: AsyncClient) -> None:
        owner_a = await _auth_headers(client)
        project = await _create_project(client, owner_a)
        task = await _create_task_under_project(client, owner_a, project["id"])
        owner_b = await _auth_headers(client)

        resp = await client.get(f"/api/v1/tasks/{task['id']}", headers=owner_b)
        assert resp.status_code == 404

    async def test_patch_task_status_200(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        project = await _create_project(client, headers)
        task = await _create_task_under_project(client, headers, project["id"])

        resp = await client.patch(
            f"/api/v1/tasks/{task['id']}",
            json={"status": "in_progress"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "in_progress"

    async def test_delete_task_204(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        project = await _create_project(client, headers)
        task = await _create_task_under_project(client, headers, project["id"])

        resp = await client.delete(f"/api/v1/tasks/{task['id']}", headers=headers)
        assert resp.status_code == 204
        follow = await client.get(f"/api/v1/tasks/{task['id']}", headers=headers)
        assert follow.status_code == 404


class TestChecklist:
    async def test_create_checklist_item_201(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        project = await _create_project(client, headers)
        task = await _create_task_under_project(client, headers, project["id"])

        resp = await client.post(
            f"/api/v1/tasks/{task['id']}/checklist",
            json={"text": "Bước 1", "position": 0},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["text"] == "Bước 1"
        assert data["is_done"] is False
        assert data["task_id"] == task["id"]

        # appears on the task detail
        detail = await client.get(f"/api/v1/tasks/{task['id']}", headers=headers)
        assert len(detail.json()["data"]["checklist_items"]) == 1

    async def test_toggle_checklist_item_200(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        project = await _create_project(client, headers)
        task = await _create_task_under_project(client, headers, project["id"])
        created = await client.post(
            f"/api/v1/tasks/{task['id']}/checklist",
            json={"text": "Bước 1"},
            headers=headers,
        )
        item = created.json()["data"]

        resp = await client.patch(
            f"/api/v1/tasks/{task['id']}/checklist/{item['id']}",
            json={"is_done": True},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["is_done"] is True

    async def test_delete_checklist_item_204(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        project = await _create_project(client, headers)
        task = await _create_task_under_project(client, headers, project["id"])
        created = await client.post(
            f"/api/v1/tasks/{task['id']}/checklist",
            json={"text": "Bước 1"},
            headers=headers,
        )
        item = created.json()["data"]

        resp = await client.delete(
            f"/api/v1/tasks/{task['id']}/checklist/{item['id']}", headers=headers
        )
        assert resp.status_code == 204
