"""Unit tests cho AiJobsService._dispatch — nhánh broker chết.

Dòng job được `commit()` TRƯỚC khi xếp lệnh (worker mở kết nối riêng, phải thấy được nó).
Nên `.delay()` ném lỗi mà không ai bắt thì route trả 500 trong khi dòng job vẫn nằm đó ở
trạng thái `queued`: không worker nào nhận, không ai dọn, màn hình quay vòng mãi.  #Huynh
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.modules.ai_jobs.application.service import AiJobsService
from src.modules.ai_jobs.domain.value_objects.status import AiJobStatus, can_transition
from src.shared.responses.error import ErrorCode


def _job(job_type: str = "lead_qualifier") -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), type=job_type, status=AiJobStatus.QUEUED.value)


class TestDispatch:
    async def test_broker_song_thi_xep_lenh_nhu_cu(self) -> None:
        repo = AsyncMock()
        job = _job()
        called: list[str] = []

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(
                "src.workers.ai_jobs.tasks.qualify_deal_async_by_job_id.delay",
                lambda job_id: called.append(job_id),
            )
            await AiJobsService(db=AsyncMock(), repo=repo)._dispatch(job)

        assert called == [str(job.id)]
        repo.mark_failed.assert_not_awaited()

    async def test_broker_chet_thi_khong_nem_len_nguoi_goi(self) -> None:
        repo = AsyncMock()

        def _broker_died(*_args: object) -> None:
            raise ConnectionError("Error 111 connecting to redis:6379. Connection refused.")

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("src.workers.ai_jobs.tasks.qualify_deal_async_by_job_id.delay", _broker_died)
            await AiJobsService(db=AsyncMock(), repo=repo)._dispatch(_job())

    async def test_broker_chet_thi_chot_job_thanh_failed_kem_cau_tieng_viet(self) -> None:
        repo = AsyncMock()
        job = _job("proposal_generator")

        def _broker_died(*_args: object) -> None:
            raise OSError("broker unreachable")

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("src.workers.ai_jobs.tasks.generate_proposal_async.delay", _broker_died)
            await AiJobsService(db=AsyncMock(), repo=repo)._dispatch(job)

        repo.mark_failed.assert_awaited_once()
        marked_job, error = repo.mark_failed.await_args.args
        assert marked_job is job
        assert error.code == ErrorCode.INTERNAL_SERVER_ERROR.value
        # Người dùng đọc câu này trên màn hình: phải là tiếng Việt và nói rõ làm gì tiếp.
        assert "hàng đợi" in error.message
        assert "chạy lại" in error.message
        # Hàng đợi sống lại là chạy được -> màn hình phải mời thử lại, không phải "nâng gói".
        assert error.retryable is True

    def test_queued_duoc_phep_chuyen_thang_sang_failed(self) -> None:
        """Không xếp nổi lệnh thì job hỏng thật, chứ không phải đang chờ tới lượt."""
        assert can_transition(AiJobStatus.QUEUED, AiJobStatus.FAILED) is True
