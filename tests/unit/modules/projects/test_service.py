"""Unit tests for ProjectService (mocked repository, no DB)."""

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.modules.projects.application.service import ProjectService
from src.modules.projects.schemas.request import CreateProjectRequest
from src.shared.exceptions.domain import NotFoundError


def _project_stub(**overrides: object) -> Any:
    base: dict[str, Any] = {
        "id": uuid.uuid4(),
        "owner_id": uuid.uuid4(),
        "deal_id": None,
        "name": "Website redesign",
        "status": "planning",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


async def test_create_project_returns_project() -> None:
    owner = uuid.uuid4()
    repo = AsyncMock()
    repo.create.return_value = _project_stub(owner_id=owner, name="Website redesign")
    service = ProjectService(db=AsyncMock(), repo=repo)

    result = await service.create(owner, CreateProjectRequest(name="Website redesign"))

    assert result.name == "Website redesign"
    repo.create.assert_awaited_once()
    assert repo.create.await_args.kwargs["owner_id"] == owner


async def test_create_project_without_deal_skips_deal_lookup() -> None:
    owner = uuid.uuid4()
    repo = AsyncMock()
    repo.create.return_value = _project_stub(owner_id=owner)
    service = ProjectService(db=AsyncMock(), repo=repo)

    await service.create(owner, CreateProjectRequest(name="No deal"))

    repo.get_deal_by_id.assert_not_awaited()


async def test_create_project_with_own_deal_passes_deal_id() -> None:
    owner = uuid.uuid4()
    deal_id = uuid.uuid4()
    repo = AsyncMock()
    repo.get_deal_by_id.return_value = SimpleNamespace(id=deal_id, owner_user_id=owner)
    repo.create.return_value = _project_stub(owner_id=owner, deal_id=deal_id)
    service = ProjectService(db=AsyncMock(), repo=repo)

    result = await service.create(owner, CreateProjectRequest(name="Có deal", deal_id=deal_id))

    assert result.deal_id == deal_id
    repo.get_deal_by_id.assert_awaited_once_with(deal_id, owner)
    assert repo.create.await_args.kwargs["deal_id"] == deal_id


async def test_create_project_rejects_deal_of_another_owner() -> None:
    """Deal không thuộc người gọi -> 404, và KHÔNG được ghi hàng mồ côi nào."""
    owner = uuid.uuid4()
    deal_id = uuid.uuid4()
    repo = AsyncMock()
    repo.get_deal_by_id.return_value = None  # owner filter loại deal của tenant khác
    service = ProjectService(db=AsyncMock(), repo=repo)

    with pytest.raises(NotFoundError) as err:
        await service.create(owner, CreateProjectRequest(name="Stolen", deal_id=deal_id))

    assert "không tìm thấy deal" in str(err.value).lower()
    repo.create.assert_not_awaited()


async def test_get_project_raises_not_found_for_wrong_owner() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = None  # owner filter excludes other tenant's project
    service = ProjectService(db=AsyncMock(), repo=repo)

    with pytest.raises(NotFoundError):
        await service.get(uuid.uuid4(), uuid.uuid4())


async def test_list_projects_filters_by_deal_id() -> None:
    deal_id = uuid.uuid4()
    owner = uuid.uuid4()
    repo = AsyncMock()
    repo.list.return_value = ([_project_stub(deal_id=deal_id)], 1)
    service = ProjectService(db=AsyncMock(), repo=repo)

    items, total = await service.list(owner, deal_id=deal_id, page=1, page_size=20)

    assert total == 1
    assert items[0].deal_id == deal_id
    assert repo.list.await_args.kwargs["deal_id"] == deal_id


async def test_get_or_create_for_deal_creates_if_none() -> None:
    deal_id = uuid.uuid4()
    owner = uuid.uuid4()
    repo = AsyncMock()
    repo.get_by_deal_id.return_value = None
    repo.create.return_value = _project_stub(deal_id=deal_id, owner_id=owner)
    service = ProjectService(db=AsyncMock(), repo=repo)

    result = await service.get_or_create_for_deal(deal_id, owner)

    assert result.deal_id == deal_id
    repo.create.assert_awaited_once()


async def test_get_or_create_for_deal_returns_existing() -> None:
    deal_id = uuid.uuid4()
    owner = uuid.uuid4()
    existing = _project_stub(deal_id=deal_id, owner_id=owner)
    repo = AsyncMock()
    repo.get_by_deal_id.return_value = existing
    service = ProjectService(db=AsyncMock(), repo=repo)

    result = await service.get_or_create_for_deal(deal_id, owner)

    assert result is existing
    repo.create.assert_not_awaited()
