"""Khâu commit của task gửi lời nhắc — chỗ từng làm khách nhận thư lặp mỗi 60 giây.

Thân task mở engine thật nên không mock được trọn; nhưng phần quyết định "commit hỏng
thì làm gì" đã tách thành `_commit_after_delivery`, và ĐÓ mới là chỗ có bug. Cùng lối
với `test_ai_jobs_tasks.py`: test đúng cái helper, không giả lập cả Celery.
"""

import uuid
from unittest.mock import AsyncMock

import pytest

from src.workers.reminder_jobs.tasks import _commit_after_delivery


class TestCommitSauKhiGui:
    async def test_commit_xuoi_thi_khong_lam_gi_them(self) -> None:
        session = AsyncMock()

        await _commit_after_delivery(session, str(uuid.uuid4()), delivered=True)

        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()
        session.execute.assert_not_awaited()

    async def test_chua_gui_duoc_ma_commit_hong_thi_de_loi_bay_len(self) -> None:
        """Chưa gửi thì `pending` là ĐÚNG — lượt sau gửi lại mới là điều ta muốn."""
        session = AsyncMock()
        session.commit.side_effect = RuntimeError("mất kết nối DB")

        with pytest.raises(RuntimeError):
            await _commit_after_delivery(session, str(uuid.uuid4()), delivered=False)

        session.execute.assert_not_awaited()

    async def test_da_gui_roi_ma_commit_hong_thi_van_chot_sent(self) -> None:
        """Vết chính: commit vỡ sau khi thư đã đi → transaction cuộn lại → lời nhắc quay
        về `pending` → beat quét lại sau 60 giây → KHÁCH NHẬN LẠI ĐÚNG LÁ THƯ ĐÓ."""
        session = AsyncMock()
        session.commit.side_effect = [
            RuntimeError("value too long for type character varying(200)"),
            None,
        ]
        reminder_id = str(uuid.uuid4())

        await _commit_after_delivery(session, reminder_id, delivered=True)

        session.rollback.assert_awaited_once()
        session.execute.assert_awaited_once()
        assert session.commit.await_count == 2

        stmt = session.execute.await_args.args[0]
        assert "UPDATE reminders" in str(stmt)
        params = stmt.compile().params
        assert params["status"] == "sent"
        # Chỉ chạm hàng còn đang chờ, và đúng hàng của lời nhắc này.
        assert str(params["id_1"]) == reminder_id
        assert params["status_1"] == "pending"
