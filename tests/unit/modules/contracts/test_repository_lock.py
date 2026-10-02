"""Khoá hàng ở repository hợp đồng, và chỉ mục "mỗi deal một hợp đồng sống".

Hình dạng lỗi lấy từ lần chạy thật (SQLAlchemy 2 + asyncpg): `DBAPIError.orig` là bản dịch của
adapter, lỗi asyncpg gốc nằm ở `__cause__` của nó.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.sql import Executable

from src.modules.contracts.infrastructure.repository import (
    ContractsRepository,
    LiveContractExistsError,
    RowLockedError,
)

CONTRACT_ID = uuid.uuid4()
DEAL_ID = uuid.uuid4()
OWNER_ID = uuid.uuid4()


def _sql(statement: Executable) -> str:
    return " ".join(str(statement.compile(dialect=postgresql.dialect())).split())


def _db_error(*, adapter_sqlstate: str | None, cause: BaseException | None) -> DBAPIError:
    orig = Exception("adapter error")
    if adapter_sqlstate is not None:
        orig.sqlstate = adapter_sqlstate  # type: ignore[attr-defined]
        orig.pgcode = adapter_sqlstate  # type: ignore[attr-defined]
    orig.__cause__ = cause
    return DBAPIError("SELECT ... FOR NO KEY UPDATE NOWAIT", {}, orig)


def _repo(*, scalar: object = None, error: Exception | None = None) -> ContractsRepository:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=scalar, side_effect=error)
    return ContractsRepository(db=db)


def _statement(repo: ContractsRepository) -> Executable:
    return repo.db.scalar.await_args.args[0]


class TestCauSqlKhoaHang:
    async def test_hop_dong_khoa_for_no_key_update_khong_nowait_theo_mac_dinh(self) -> None:
        repo = _repo(scalar="row")

        result = await repo.get_by_id_for_update(CONTRACT_ID, OWNER_ID)

        assert result == "row"
        sql = _sql(_statement(repo))
        assert sql.endswith("FOR NO KEY UPDATE")
        assert "NOWAIT" not in sql
        assert "contracts.id = " in sql
        assert "contracts.owner_user_id = " in sql

    async def test_nowait_thi_cau_sql_co_nowait(self) -> None:
        repo = _repo()

        await repo.get_by_id_for_update(CONTRACT_ID, OWNER_ID, nowait=True)

        assert _sql(_statement(repo)).endswith("FOR NO KEY UPDATE NOWAIT")

    async def test_deal_khoa_for_no_key_update_theo_id_va_chu_so_huu(self) -> None:
        repo = _repo(scalar="deal")

        result = await repo.get_deal_for_update(DEAL_ID, OWNER_ID, nowait=True)

        assert result == "deal"
        sql = _sql(_statement(repo))
        assert sql.endswith("FOR NO KEY UPDATE NOWAIT")
        assert "deals.id = " in sql
        assert "deals.owner_user_id = " in sql

    async def test_doc_lai_cot_tu_db_du_object_da_nam_trong_phien(self) -> None:
        repo = _repo()

        await repo.get_by_id_for_update(CONTRACT_ID, OWNER_ID)
        await repo.get_deal_for_update(DEAL_ID, OWNER_ID)

        for call in repo.db.scalar.await_args_list:
            assert call.args[0].get_execution_options().get("populate_existing") is True

    async def test_cau_hoi_hop_dong_song_khop_dieu_kien_cua_chi_muc(self) -> None:
        """Đúng điều kiện của `uq_contracts_one_active_per_deal`: active / pending_signatures,
        cùng deal, và KHÔNG tính chính hợp đồng đang gửi."""
        repo = _repo(scalar="khac")

        result = await repo.get_live_contract_for_deal(DEAL_ID, CONTRACT_ID)

        assert result == "khac"
        sql = _sql(_statement(repo))
        assert "contracts.deal_id = " in sql
        assert "contracts.id != " in sql
        assert "contracts.status IN " in sql
        assert "LIMIT" in sql


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
            await getattr(repo, method)(CONTRACT_ID, OWNER_ID, nowait=True)

        assert bat.value.__cause__ is error

    @pytest.mark.parametrize("method", ["get_by_id_for_update", "get_deal_for_update"])
    async def test_deadlock_la_loi_khac_thi_di_qua_nguyen_ven(self, method: str) -> None:
        deadlock = _db_error(
            adapter_sqlstate="40P01", cause=asyncpg.exceptions.DeadlockDetectedError("deadlock")
        )
        repo = _repo(error=deadlock)

        with pytest.raises(DBAPIError) as bat:
            await getattr(repo, method)(CONTRACT_ID, OWNER_ID, nowait=True)

        assert bat.value is deadlock

    @pytest.mark.parametrize("method", ["get_by_id_for_update", "get_deal_for_update"])
    async def test_khong_nowait_thi_khong_dich_gi_ca(self, method: str) -> None:
        locked = _db_error(
            adapter_sqlstate="55P03",
            cause=asyncpg.exceptions.LockNotAvailableError("canceling statement due to lock timeout"),
        )
        repo = _repo(error=locked)

        with pytest.raises(DBAPIError) as bat:
            await getattr(repo, method)(CONTRACT_ID, OWNER_ID)

        assert bat.value is locked


def _unique_violation(*, constraint_name: str | None, message: str) -> IntegrityError:
    cause = asyncpg.exceptions.UniqueViolationError(message)
    if constraint_name is not None:
        cause.constraint_name = constraint_name
    orig = Exception(f"<class 'asyncpg.exceptions.UniqueViolationError'>: {message}")
    orig.__cause__ = cause
    return IntegrityError("UPDATE contracts SET status=$1", {}, orig)


class TestLuuHopDongVaoHangSong:
    async def test_luu_thanh_cong_thi_tra_ve_hop_dong(self) -> None:
        repo = ContractsRepository(db=AsyncMock())
        contract = MagicMock()

        result = await repo.save_entering_live_status(contract)

        assert result is contract
        repo.db.flush.assert_awaited_once()
        repo.db.refresh.assert_awaited_once_with(contract)

    @pytest.mark.parametrize(
        "error",
        [
            pytest.param(
                _unique_violation(
                    constraint_name="uq_contracts_one_active_per_deal",
                    message='duplicate key value violates unique constraint '
                    '"uq_contracts_one_active_per_deal"',
                ),
                id="co-constraint_name-cua-asyncpg",
            ),
            pytest.param(
                _unique_violation(
                    constraint_name=None,
                    message='duplicate key value violates unique constraint '
                    '"uq_contracts_one_active_per_deal"',
                ),
                id="chi-co-trong-cau-bao-loi",
            ),
        ],
    )
    async def test_chi_muc_tu_choi_thi_nem_LiveContractExistsError(
        self, error: IntegrityError
    ) -> None:
        db = AsyncMock()
        db.flush.side_effect = error
        repo = ContractsRepository(db=db)

        with pytest.raises(LiveContractExistsError) as bat:
            await repo.save_entering_live_status(MagicMock())

        assert bat.value.__cause__ is error

    async def test_rang_buoc_khac_vi_pham_thi_di_qua_nguyen_ven(self) -> None:
        """Chỉ nhận ra ĐÚNG chỉ mục này — một vi phạm duy nhất khác (trùng version) không được
        giả làm "deal đã có hợp đồng khác"."""
        other = _unique_violation(
            constraint_name="uq_contracts_deal_version",
            message='duplicate key value violates unique constraint "uq_contracts_deal_version"',
        )
        db = AsyncMock()
        db.flush.side_effect = other
        repo = ContractsRepository(db=db)

        with pytest.raises(IntegrityError) as bat:
            await repo.save_entering_live_status(MagicMock())

        assert bat.value is other
