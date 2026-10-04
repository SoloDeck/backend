"""Chi phí AI của admin: tìm theo người dùng, lọc theo tính năng, phân trang.

Con số TỔNG phải theo đúng tập đang lọc. Trang này từng chỉ tải 50 dòng đầu, không có ô tìm hay bộ
lọc nên dòng thứ 51 trở đi vô hình. Mọi thứ lọc/phân trang làm ở máy chủ; con số tổng ở đầu trang
phải khớp với những gì đang lọc, không phải toàn hệ thống.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import AiCostRecordModel
from tests.integration.modules.admin.test_admin_api import _admin_headers


async def _nguoi_dung(client: AsyncClient, db_session: AsyncSession, ten: str) -> tuple[str, str]:
    """Đăng ký một freelancer có tên cho trước; trả (id, email)."""
    email = f"{uuid.uuid4().hex[:8]}@example.com"
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Test@1234!", "full_name": ten},
    )
    assert resp.status_code == 201, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    me = await client.get("/api/v1/users/me", headers=headers)
    return me.json()["data"]["id"], email


async def _ghi(
    db_session: AsyncSession,
    user_id: str,
    module: str,
    *,
    tok_in: int = 100,
    tok_out: int = 10,
    usd: str = "0.001",
    phut_truoc: int = 0,
) -> None:
    await db_session.execute(
        insert(AiCostRecordModel).values(
            id=uuid.uuid4(),
            user_id=uuid.UUID(user_id),
            ai_module=module,
            model_used="gemini-2.5-flash",
            input_tokens=tok_in,
            output_tokens=tok_out,
            estimated_cost_usd=Decimal(usd),
            status="completed",
            occurred_at=datetime.now(UTC) - timedelta(minutes=phut_truoc),
        )
    )
    await db_session.flush()


async def _lay(client: AsyncClient, headers: dict, **params) -> dict:
    resp = await client.get("/api/v1/admin/ai-costs", params=params, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


class TestTimTheoNguoiDung:
    async def test_tim_theo_email_chi_con_dong_cua_nguoi_do(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = await _admin_headers(client, db_session)
        a_id, a_mail = await _nguoi_dung(client, db_session, "An Nguyen")
        b_id, _ = await _nguoi_dung(client, db_session, "Binh Tran")
        await _ghi(db_session, a_id, "lead_qualifier")
        await _ghi(db_session, b_id, "lead_qualifier")

        body = await _lay(client, admin, search=a_mail)

        assert body["total"] == 1
        assert [r["user_id"] for r in body["data"]] == [a_id]

    async def test_tim_theo_ten_khong_phan_biet_hoa_thuong(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = await _admin_headers(client, db_session)
        a_id, _ = await _nguoi_dung(client, db_session, "An Nguyen")
        b_id, _ = await _nguoi_dung(client, db_session, "Binh Tran")
        await _ghi(db_session, a_id, "proposal_generator")
        await _ghi(db_session, b_id, "proposal_generator")

        body = await _lay(client, admin, search="  bINH  ")

        assert [r["user_id"] for r in body["data"]] == [b_id]

    async def test_tim_khong_ra_ai_thi_rong_va_tong_bang_0(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = await _admin_headers(client, db_session)
        a_id, _ = await _nguoi_dung(client, db_session, "An Nguyen")
        await _ghi(db_session, a_id, "lead_qualifier", tok_in=500)

        body = await _lay(client, admin, search="khong-co-ai-ten-nhu-vay")

        assert body["total"] == 0 and body["data"] == []
        assert body["totals"]["input_tokens"] == 0

    async def test_o_tim_trong_thi_khong_loc(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = await _admin_headers(client, db_session)
        a_id, _ = await _nguoi_dung(client, db_session, "An Nguyen")
        await _ghi(db_session, a_id, "lead_qualifier")

        co_ma_trong = await _lay(client, admin, search="   ")
        khong_tim = await _lay(client, admin)

        assert co_ma_trong["total"] == khong_tim["total"] >= 1


class TestLocTheoTinhNang:
    async def test_chi_tra_dong_cua_tinh_nang_da_chon(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = await _admin_headers(client, db_session)
        a_id, a_mail = await _nguoi_dung(client, db_session, "An Nguyen")
        await _ghi(db_session, a_id, "lead_qualifier")
        await _ghi(db_session, a_id, "proposal_generator")
        await _ghi(db_session, a_id, "proposal_generator")

        body = await _lay(client, admin, search=a_mail, ai_module="proposal_generator")

        assert body["total"] == 2
        assert {r["ai_module"] for r in body["data"]} == {"proposal_generator"}

    async def test_tinh_nang_va_nguoi_dung_ket_hop_duoc(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = await _admin_headers(client, db_session)
        a_id, a_mail = await _nguoi_dung(client, db_session, "An Nguyen")
        b_id, _ = await _nguoi_dung(client, db_session, "Binh Tran")
        await _ghi(db_session, a_id, "contract_generator")
        await _ghi(db_session, b_id, "contract_generator")
        await _ghi(db_session, a_id, "followup_generator")

        body = await _lay(client, admin, search=a_mail, ai_module="contract_generator")

        assert [(r["user_id"], r["ai_module"]) for r in body["data"]] == [
            (a_id, "contract_generator")
        ]


class TestPhanTrang:
    async def test_chia_trang_that_va_khong_mat_dong_nao(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = await _admin_headers(client, db_session)
        a_id, a_mail = await _nguoi_dung(client, db_session, "An Nguyen")
        for i in range(7):
            await _ghi(db_session, a_id, "lead_qualifier", phut_truoc=i)

        p1 = await _lay(client, admin, search=a_mail, page=1, page_size=3)
        p2 = await _lay(client, admin, search=a_mail, page=2, page_size=3)
        p3 = await _lay(client, admin, search=a_mail, page=3, page_size=3)

        assert p1["total"] == p2["total"] == p3["total"] == 7
        assert [len(p["data"]) for p in (p1, p2, p3)] == [3, 3, 1]
        ids = [r["id"] for p in (p1, p2, p3) for r in p["data"]]
        assert len(set(ids)) == 7  # không trùng, không sót
        # Mới nhất trước: thời điểm không tăng dần qua các trang.
        times = [r["occurred_at"] for p in (p1, p2, p3) for r in p["data"]]
        assert times == sorted(times, reverse=True)


class TestTongTheoTapDangLoc:
    async def test_tong_chi_cong_cac_dong_dang_loc(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = await _admin_headers(client, db_session)
        a_id, a_mail = await _nguoi_dung(client, db_session, "An Nguyen")
        b_id, _ = await _nguoi_dung(client, db_session, "Binh Tran")
        await _ghi(db_session, a_id, "lead_qualifier", tok_in=100, tok_out=10, usd="0.5")
        await _ghi(db_session, a_id, "lead_qualifier", tok_in=200, tok_out=20, usd="0.25")
        await _ghi(db_session, b_id, "lead_qualifier", tok_in=9000, tok_out=900, usd="9")

        body = await _lay(client, admin, search=a_mail)

        assert body["totals"]["input_tokens"] == 300
        assert body["totals"]["output_tokens"] == 30
        assert Decimal(str(body["totals"]["estimated_cost_usd"])) == Decimal("0.75")

    async def test_tong_theo_tinh_nang_cung_chi_cong_tinh_nang_do(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = await _admin_headers(client, db_session)
        a_id, a_mail = await _nguoi_dung(client, db_session, "An Nguyen")
        await _ghi(db_session, a_id, "lead_qualifier", tok_in=100)
        await _ghi(db_session, a_id, "followup_generator", tok_in=40)

        body = await _lay(client, admin, search=a_mail, ai_module="followup_generator")

        assert body["totals"]["input_tokens"] == 40


class TestChiAdminDuocXem:
    async def test_tim_kiem_khong_mo_cua_cho_nguoi_thuong(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, email = await _nguoi_dung(client, db_session, "An Nguyen")
        login = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "Test@1234!"}
        )
        headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}

        resp = await client.get("/api/v1/admin/ai-costs", params={"search": "a"}, headers=headers)

        assert resp.status_code == 403

    async def test_o_tim_qua_dai_bi_tu_choi(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = await _admin_headers(client, db_session)

        resp = await client.get(
            "/api/v1/admin/ai-costs", params={"search": "x" * 101}, headers=admin
        )

        assert resp.status_code == 422
