"""Khoá hàng ở repository: câu SQL đúng, và "không giành được khoá" được dịch đúng thành `RowLockedError`.

`nowait=True` chỉ có nghĩa khi Postgres thật sự từ chối ngay. Hình dạng lỗi dưới đây lấy từ lần chạy
thật (SQLAlchemy 2 + asyncpg): `DBAPIError.orig` là bản dịch của adapter có `sqlstate`, và lỗi asyncpg
gốc `LockNotAvailableError` (sqlstate `55P03`) nằm ở `__cause__` của nó.
"""

import uuid
from unittest.mock import AsyncMock

import asyncpg
import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError
from sqlalchemy.sql import Executable

from src.modules.proposals.infrastructure.repository import ProposalsRepository, RowLockedError

PROPOSAL_ID = uuid.uuid4()
DEAL_ID = uuid.uuid4()
OWNER_ID = uuid.uuid4()


def _sql(statement: Executable) -> str:
    return " ".join(str(statement.compile(dialect=postgresql.dialect())).split())


def _db_error(*, adapter_sqlstate: str | None, cause: BaseException | None) -> DBAPIError:
    """Lỗi DB có hình dạng như thật: lỗi adapter ở `orig`, lỗi asyncpg gốc ở `orig.__cause__`."""
    orig = Exception("adapter error")
    if adapter_sqlstate is not None:
        orig.sqlstate = adapter_sqlstate  # type: ignore[attr-defined]
        orig.pgcode = adapter_sqlstate  # type: ignore[attr-defined]
    orig.__cause__ = cause
    return DBAPIError("SELECT ... FOR NO KEY UPDATE NOWAIT", {}, orig)


def _repo(*, scalar: object = None, error: Exception | None = None) -> ProposalsRepository:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=scalar, side_effect=error)
    return ProposalsRepository(db=db)


def _statement(repo: ProposalsRepository) -> Executable:
    return repo.db.scalar.await_args.args[0]


class TestCauSqlKhoaHang:
    async def test_bao_gia_khoa_for_no_key_update_khong_nowait_theo_mac_dinh(self) -> None:
        repo = _repo(scalar="row")

        result = await repo.get_by_id_for_update(PROPOSAL_ID, OWNER_ID)

        assert result == "row"
        sql = _sql(_statement(repo))
        assert sql.endswith("FOR NO KEY UPDATE")
        assert "NOWAIT" not in sql

    async def test_nowait_thi_cau_sql_co_nowait(self) -> None:
        repo = _repo()

        await repo.get_by_id_for_update(PROPOSAL_ID, OWNER_ID, nowait=True)

        assert _sql(_statement(repo)).endswith("FOR NO KEY UPDATE NOWAIT")

    async def test_bao_gia_loc_theo_id_va_chu_so_huu(self) -> None:
        repo = _repo()

        await repo.get_by_id_for_update(PROPOSAL_ID, OWNER_ID)

        sql = _sql(_statement(repo))
        assert "proposals.id = " in sql
        assert "proposals.owner_user_id = " in sql

    async def test_doc_lai_cot_tu_db_du_object_da_nam_trong_phien(self) -> None:
        """Không có `populate_existing`, object đã nạp sẵn giữ nguyên giá trị cũ dù hàng đã đổi —
        mà đọc LẠI trạng thái sau khi giữ khoá chính là cả mục đích của việc khoá."""
        repo = _repo()

        await repo.get_by_id_for_update(PROPOSAL_ID, OWNER_ID)
        await repo.get_deal_for_update(DEAL_ID, OWNER_ID)

        for call in repo.db.scalar.await_args_list:
            assert call.args[0].get_execution_options().get("populate_existing") is True

    async def test_deal_khoa_for_no_key_update_theo_id_va_chu_so_huu(self) -> None:
        repo = _repo(scalar="deal")

        result = await repo.get_deal_for_update(DEAL_ID, OWNER_ID)

        assert result == "deal"
        sql = _sql(_statement(repo))
        assert sql.endswith("FOR NO KEY UPDATE")
        assert "deals.id = " in sql
        assert "deals.owner_user_id = " in sql

    async def test_deal_nowait_thi_cau_sql_co_nowait(self) -> None:
        repo = _repo()

        await repo.get_deal_for_update(DEAL_ID, OWNER_ID, nowait=True)

        assert _sql(_statement(repo)).endswith("FOR NO KEY UPDATE NOWAIT")


class TestDichLoiKhongGianhDuocKhoa:
    @pytest.mark.parametrize(
        "error",
        [
            pytest.param(
                _db_error(
                    adapter_sqlstate="55P03",
                    cause=asyncpg.exceptions.LockNotAvailableError("could not obtain lock"),
                ),
                id="hinh-dang-that-ca-hai-lop",
            ),
            pytest.param(
                _db_error(
                    adapter_sqlstate=None,
                    cause=asyncpg.exceptions.LockNotAvailableError("could not obtain lock"),
                ),
                id="chi-lop-asyncpg-goc",
            ),
            pytest.param(
                _db_error(adapter_sqlstate="55P03", cause=None), id="chi-lop-adapter"
            ),
        ],
    )
    @pytest.mark.parametrize("method", ["get_by_id_for_update", "get_deal_for_update"])
    async def test_nowait_bi_khoa_thi_nem_RowLockedError(
        self, method: str, error: DBAPIError
    ) -> None:
        repo = _repo(error=error)

        with pytest.raises(RowLockedError) as bat:
            await getattr(repo, method)(PROPOSAL_ID, OWNER_ID, nowait=True)

        assert bat.value.__cause__ is error  # giữ lỗi gốc để còn truy nguyên

    @pytest.mark.parametrize("method", ["get_by_id_for_update", "get_deal_for_update"])
    async def test_deadlock_la_loi_khac_thi_di_qua_nguyen_ven(self, method: str) -> None:
        deadlock = _db_error(
            adapter_sqlstate="40P01", cause=asyncpg.exceptions.DeadlockDetectedError("deadlock")
        )
        repo = _repo(error=deadlock)

        with pytest.raises(DBAPIError) as bat:
            await getattr(repo, method)(PROPOSAL_ID, OWNER_ID, nowait=True)

        assert bat.value is deadlock

    @pytest.mark.parametrize("method", ["get_by_id_for_update", "get_deal_for_update"])
    async def test_khong_nowait_thi_khong_dich_gi_ca(self, method: str) -> None:
        """55P03 mà không xin NOWAIT chỉ có thể do `lock_timeout` — đừng giả làm "đang bận"."""
        locked = _db_error(
            adapter_sqlstate="55P03",
            cause=asyncpg.exceptions.LockNotAvailableError("canceling statement due to lock timeout"),
        )
        repo = _repo(error=locked)

        with pytest.raises(DBAPIError) as bat:
            await getattr(repo, method)(PROPOSAL_ID, OWNER_ID)

        assert bat.value is locked
