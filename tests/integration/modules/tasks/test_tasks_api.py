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


class TestThuTuTaskOnDinh:
    """Thứ tự task phải TẤT ĐỊNH, kể cả khi cả lô sinh trong cùng một transaction.

    Bản trước sắp theo `created_at DESC` trần. `created_at` dùng `server_default=func.now()`,
    mà `now()` của PostgreSQL trả về thời điểm bắt đầu TRANSACTION — nên các task sinh cùng lô
    có `created_at` bằng nhau tới từng micro giây, và `ORDER BY created_at` là hoà hoàn toàn:
    thứ tự do planner quyết, F5 hai lần ra hai kiểu.

    Chuyện này thành lỗi nghiệp vụ từ khi freelancer kéo sắp lại được hạng mục chi phí ở mục 7
    của báo giá — sắp đúng trình tự triển khai rồi mở bảng việc ra vẫn thấy lộn xộn.  #Huynh
    """

    async def test_task_giu_dung_thu_tu_tao(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        project = await _create_project(client, headers)

        titles = ["Thiết kế giao diện", "Tích hợp đặt lịch", "Phát triển ứng dụng"]
        for title in titles:
            resp = await client.post(
                f"/api/v1/projects/{project['id']}/tasks",
                json={"title": title},
                headers=headers,
            )
            assert resp.status_code == 201, resp.text

        listed = await client.get(f"/api/v1/projects/{project['id']}/tasks", headers=headers)
        assert listed.status_code == 200, listed.text
        rows = listed.json()["data"]
        assert [r["title"] for r in rows] == titles
        assert [r["position"] for r in rows] == [0, 1, 2]

    async def test_sua_mot_task_khong_lam_xao_tron_thu_tu(self, client: AsyncClient) -> None:
        """Chính là chỗ bản cũ trượt, và là cảnh người dùng gặp thật.

        `ORDER BY created_at DESC` không có khoá phá hoà. Khi các dòng bằng nhau, thứ tự trả
        về là thứ tự nằm trong heap — mà PostgreSQL ghi bản cập nhật thành một phiên bản MỚI
        ở cuối heap. Nên chỉ cần đổi tên hay tick xong một công việc là cả danh sách nhảy chỗ,
        dòng vừa sửa rơi xuống cuối. Người dùng đang nhìn thì thấy bảng tự xáo.  #Huynh
        """
        headers = await _auth_headers(client)
        project = await _create_project(client, headers)
        for index in range(5):
            await client.post(
                f"/api/v1/projects/{project['id']}/tasks",
                json={"title": f"Việc {index}"},
                headers=headers,
            )

        before = await client.get(f"/api/v1/projects/{project['id']}/tasks", headers=headers)
        order_before = [r["id"] for r in before.json()["data"]]

        edited = await client.patch(
            f"/api/v1/tasks/{order_before[0]}",
            json={"title": "Việc 0 (đã đổi tên)"},
            headers=headers,
        )
        assert edited.status_code == 200, edited.text

        after = await client.get(f"/api/v1/projects/{project['id']}/tasks", headers=headers)
        assert [r["id"] for r in after.json()["data"]] == order_before

    async def test_task_them_sau_noi_tiep_chu_khong_dam_len(self, client: AsyncClient) -> None:
        headers = await _auth_headers(client)
        project = await _create_project(client, headers)
        await _create_task_under_project(client, headers, project["id"])
        await _create_task_under_project(client, headers, project["id"])
        await _create_task_under_project(client, headers, project["id"])

        listed = await client.get(f"/api/v1/projects/{project['id']}/tasks", headers=headers)
        positions = [r["position"] for r in listed.json()["data"]]
        assert positions == sorted(positions)
        assert len(set(positions)) == len(positions)
