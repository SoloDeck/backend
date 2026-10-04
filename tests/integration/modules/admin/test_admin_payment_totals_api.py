"""Admin: tổng giao dịch theo TOÀN BỘ tập đang lọc.

Thẻ "Đã thu / Thành công / Đang chờ" trên trang Giao dịch từng chỉ cộng các dòng của TRANG đang xem
(nên phải ghi "(trang này)"). Nay máy chủ cộng cả tập đang lọc, qua mọi trang — một con số duy nhất,
không phụ thuộc đang đứng ở trang nào. Bảng đơn giá AI thì dựng từ chính hằng số dùng để tính tiền.
"""

import uuid
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.modules.admin.test_admin_api import _admin_headers, _seed_payment


async def _nguoi_mua(client: AsyncClient, ten: str) -> tuple[str, str]:
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
    db_session: AsyncSession, user_id: str, status: str, amount: str = "100000.00", **kw
):
    """Một giao dịch; chỉ giao dịch thành công mới có ngày thanh toán."""
    if status != "succeeded":
        kw["paid_at"] = None
    await _seed_payment(
        db_session,
        user_id,
        status=status,
        amount=amount,
        provider_reference=f"REF-{uuid.uuid4().hex[:10]}",
        **kw,
    )


async def _lay(client: AsyncClient, headers: dict, **params) -> dict:
    resp = await client.get("/api/v1/admin/payments", params=params, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


class TestTongGiaoDich:
    async def test_tong_cong_het_cac_trang_chu_khong_chi_trang_dang_xem(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = await _admin_headers(client, db_session)
        uid, email = await _nguoi_mua(client, "An Nguyen")
        for _ in range(5):
            await _ghi(db_session, uid, "succeeded")
        for _ in range(3):
            await _ghi(db_session, uid, "pending")
        for _ in range(2):
            await _ghi(db_session, uid, "failed")

        body = await _lay(client, admin, search=email, page=1, page_size=2)

        assert len(body["data"]) == 2  # trang chỉ có 2 dòng
        assert body["total"] == 10
        assert Decimal(str(body["totals"]["collected_amount"])) == Decimal("500000")
        assert body["totals"]["succeeded_count"] == 5
        assert body["totals"]["pending_count"] == 3

    async def test_dang_xu_ly_tinh_la_dang_cho_con_that_bai_het_han_huy_thi_khong(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = await _admin_headers(client, db_session)
        uid, email = await _nguoi_mua(client, "An Nguyen")
        for status in ("pending", "processing", "failed", "expired", "cancelled"):
            await _ghi(db_session, uid, status)

        totals = (await _lay(client, admin, search=email))["totals"]

        assert totals["pending_count"] == 2
        assert totals["succeeded_count"] == 0
        assert Decimal(str(totals["collected_amount"])) == 0

    async def test_tong_theo_dung_bo_loc_nguoi_mua(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = await _admin_headers(client, db_session)
        a, a_mail = await _nguoi_mua(client, "An Nguyen")
        b, _ = await _nguoi_mua(client, "Binh Tran")
        await _ghi(db_session, a, "succeeded", amount="100000.00")
        await _ghi(db_session, b, "succeeded", amount="900000.00")

        totals = (await _lay(client, admin, search=a_mail))["totals"]

        assert Decimal(str(totals["collected_amount"])) == Decimal("100000")
        assert totals["succeeded_count"] == 1

    async def test_tong_theo_bo_loc_trang_thai_va_kenh(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = await _admin_headers(client, db_session)
        uid, email = await _nguoi_mua(client, "An Nguyen")
        await _ghi(db_session, uid, "succeeded", provider="momo")
        await _ghi(db_session, uid, "succeeded", provider="vnpay")
        await _ghi(db_session, uid, "pending", provider="momo")

        momo = (await _lay(client, admin, search=email, provider="momo"))["totals"]
        cho = (await _lay(client, admin, search=email, status="pending"))["totals"]

        assert momo["succeeded_count"] == 1 and momo["pending_count"] == 1
        assert cho["succeeded_count"] == 0 and cho["pending_count"] == 1
        assert Decimal(str(cho["collected_amount"])) == 0

    async def test_chi_cong_tien_dong_khong_cong_lan_don_vi_khac(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = await _admin_headers(client, db_session)
        uid, email = await _nguoi_mua(client, "An Nguyen")
        await _ghi(db_session, uid, "succeeded", amount="100000.00", currency="VND")
        await _ghi(db_session, uid, "succeeded", amount="50.00", currency="USD")

        totals = (await _lay(client, admin, search=email))["totals"]

        assert Decimal(str(totals["collected_amount"])) == Decimal("100000")
        assert totals["currency"] == "VND"

    async def test_khong_co_giao_dich_nao_thi_tong_la_0(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        admin = await _admin_headers(client, db_session)

        totals = (await _lay(client, admin, search="khong-co-ai-ten-nhu-vay"))["totals"]

        assert Decimal(str(totals["collected_amount"])) == 0
        assert totals["succeeded_count"] == 0 and totals["pending_count"] == 0
