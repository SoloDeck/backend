import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from src.modules.users.application.service import UsersService
from src.shared.exceptions.domain import NotFoundError, ValidationError


@dataclass
class UserStub:
    id: uuid.UUID
    avatar_url: str | None = None


class TestUploadAvatar:
    async def test_uploads_and_sets_avatar_url(self) -> None:
        user_id = uuid.uuid4()
        user = UserStub(id=user_id)
        repo = AsyncMock()
        repo.get_by_id.return_value = user
        repo.save.side_effect = lambda u: u
        storage = AsyncMock()
        storage.upload.return_value = "https://cdn.example.com/avatars/x/y.png"
        service = UsersService(db=AsyncMock(), repo=repo, storage=storage)

        result = await service.upload_avatar(
            user_id, content=b"fake-bytes", content_type="image/png"
        )

        storage.upload.assert_awaited_once()
        assert result.avatar_url == "https://cdn.example.com/avatars/x/y.png"

    async def test_rejects_unsupported_content_type(self) -> None:
        repo = AsyncMock()
        storage = AsyncMock()
        service = UsersService(db=AsyncMock(), repo=repo, storage=storage)

        with pytest.raises(ValidationError):
            await service.upload_avatar(
                uuid.uuid4(), content=b"fake-bytes", content_type="application/pdf"
            )
        storage.upload.assert_not_awaited()

    async def test_rejects_empty_file(self) -> None:
        repo = AsyncMock()
        storage = AsyncMock()
        service = UsersService(db=AsyncMock(), repo=repo, storage=storage)

        with pytest.raises(ValidationError):
            await service.upload_avatar(uuid.uuid4(), content=b"", content_type="image/png")

    async def test_rejects_oversized_file(self) -> None:
        repo = AsyncMock()
        storage = AsyncMock()
        service = UsersService(db=AsyncMock(), repo=repo, storage=storage)
        oversized = b"x" * (5 * 1024 * 1024 + 1)

        with pytest.raises(ValidationError):
            await service.upload_avatar(uuid.uuid4(), content=oversized, content_type="image/png")

    async def test_raises_not_found_for_unknown_user(self) -> None:
        repo = AsyncMock()
        repo.get_by_id.return_value = None
        storage = AsyncMock()
        service = UsersService(db=AsyncMock(), repo=repo, storage=storage)

        with pytest.raises(NotFoundError):
            await service.upload_avatar(
                uuid.uuid4(), content=b"fake-bytes", content_type="image/png"
            )

    async def test_raises_runtime_error_when_storage_not_initialized(self) -> None:
        repo = AsyncMock()
        service = UsersService(db=AsyncMock(), repo=repo)

        with pytest.raises(RuntimeError):
            await service.upload_avatar(
                uuid.uuid4(), content=b"fake-bytes", content_type="image/png"
            )
