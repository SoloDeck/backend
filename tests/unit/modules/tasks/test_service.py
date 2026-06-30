"""Unit tests for TaskService (mocked repository, no DB)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.modules.tasks.application.service import TaskService
from src.modules.tasks.schemas.request import CreateTaskRequest, UpdateTaskRequest
from src.shared.exceptions.domain import NotFoundError


def _task_stub(**overrides: object) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "entity_type": "project",
        "entity_id": uuid.uuid4(),
        "title": "Do the thing",
        "description": None,
        "priority": "medium",
        "status": "todo",
        "deadline": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


async def test_create_task_with_project_entity_type() -> None:
    project_id = uuid.uuid4()
    owner = uuid.uuid4()
    repo = AsyncMock()
    repo.entity_exists_for_owner.return_value = True
    repo.create.return_value = _task_stub(entity_type="project", entity_id=project_id)
    service = TaskService(db=AsyncMock(), repo=repo)

    result = await service.create_for_entity(
        "project", project_id, owner, CreateTaskRequest(title="Do the thing")
    )

    assert result.entity_type == "project"
    assert repo.create.await_args.kwargs["entity_type"] == "project"
    assert repo.create.await_args.kwargs["entity_id"] == project_id


async def test_create_task_with_deal_entity_type() -> None:
    deal_id = uuid.uuid4()
    owner = uuid.uuid4()
    repo = AsyncMock()
    repo.entity_exists_for_owner.return_value = True
    repo.create.return_value = _task_stub(entity_type="deal", entity_id=deal_id)
    service = TaskService(db=AsyncMock(), repo=repo)

    result = await service.create_for_entity(
        "deal", deal_id, owner, CreateTaskRequest(title="Follow up")
    )

    assert result.entity_type == "deal"
    assert repo.create.await_args.kwargs["entity_type"] == "deal"


async def test_create_task_raises_when_entity_not_owned() -> None:
    repo = AsyncMock()
    repo.entity_exists_for_owner.return_value = False
    service = TaskService(db=AsyncMock(), repo=repo)

    with pytest.raises(NotFoundError):
        await service.create_for_entity(
            "project", uuid.uuid4(), uuid.uuid4(), CreateTaskRequest(title="x")
        )
    repo.create.assert_not_awaited()


async def test_list_by_entity_returns_only_matching_tasks() -> None:
    project_id = uuid.uuid4()
    owner = uuid.uuid4()
    matching = [
        _task_stub(entity_type="project", entity_id=project_id),
        _task_stub(entity_type="project", entity_id=project_id),
    ]
    repo = AsyncMock()
    repo.entity_exists_for_owner.return_value = True
    repo.list_by_entity.return_value = (matching, 2)
    service = TaskService(db=AsyncMock(), repo=repo)

    items, total = await service.list_by_entity("project", project_id, owner)

    assert total == 2
    assert all(t.entity_id == project_id for t in items)
    assert repo.list_by_entity.await_args.args[0] == "project"
    assert repo.list_by_entity.await_args.args[1] == project_id


async def test_update_task_status() -> None:
    owner = uuid.uuid4()
    task = _task_stub(status="todo")
    repo = AsyncMock()
    repo.get_by_id.return_value = task
    repo.entity_exists_for_owner.return_value = True
    repo.save.side_effect = lambda t: t
    service = TaskService(db=AsyncMock(), repo=repo)

    result = await service.update(task.id, owner, UpdateTaskRequest(status="done"))

    assert result.status == "done"
    repo.save.assert_awaited_once()


async def test_get_task_raises_not_found() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = None
    service = TaskService(db=AsyncMock(), repo=repo)

    with pytest.raises(NotFoundError):
        await service.get(uuid.uuid4(), uuid.uuid4())
