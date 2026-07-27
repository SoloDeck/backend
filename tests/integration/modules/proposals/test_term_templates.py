"""Freelancer CHỌN mẫu điều khoản khi sinh báo giá.

Phủ: liệt kê mẫu theo nghề (không lộ mẫu nghề khác), sinh với mẫu đã chọn (chèn nguyên
văn), sinh với id bậy (422), và không chọn (AI tự viết, không điều khoản chuẩn).
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import insert

from src.infrastructure.database.models import SystemTemplateModel
from src.main import app
from src.shared.dependencies.ai import get_ai_facade
from tests.conftest import grant_ai_plan
from tests.integration.modules.proposals.test_generate_from_deal import (
    _PermissiveAIFacade,
    _make_deal,
)


async def _auth_with_profession(
    client: AsyncClient, db_session, profession: str | None
) -> tuple[dict, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"u_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Test@1234!",
            "full_name": "Test User",
        },
    )
    headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    me = await client.get("/api/v1/users/me", headers=headers)
    user_id = me.json()["data"]["id"]
    await grant_ai_plan(db_session, uuid.UUID(user_id))
    if profession:
        await client.patch(
            "/api/v1/users/me/freelancer-profile",
            json={"profession": profession},
            headers=headers,
        )
    return headers, user_id


async def _seed_template(
    db_session,
    *,
    admin_id: str,
    template_type: str = "proposal",
    profession: str | None = None,
    name: str = "Mẫu điều khoản",
    body: str = "Điều khoản chuẩn: đặt cọc 50%.",
    is_active: bool = True,
) -> str:
    tid = uuid.uuid4()
    await db_session.execute(
        insert(SystemTemplateModel).values(
            id=tid,
            template_type=template_type,
            name=name,
            profession=profession,
            content={"body": body},
            is_active=is_active,
            version_number=1,
            created_by_admin_id=uuid.UUID(admin_id),
        )
    )
    await db_session.flush()
    return str(tid)


@pytest.fixture(autouse=True)
def _permissive_ai():
    app.dependency_overrides[get_ai_facade] = lambda: _PermissiveAIFacade()
    yield
    app.dependency_overrides.pop(get_ai_facade, None)


class TestListTermTemplates:
    async def test_tra_mau_dung_nghe_va_dung_chung(self, client: AsyncClient, db_session) -> None:
        headers, uid = await _auth_with_profession(client, db_session, "ui-ux-design")
        await _seed_template(db_session, admin_id=uid, profession="ui-ux-design", name="Mẫu UX")
        await _seed_template(db_session, admin_id=uid, profession=None, name="Mẫu chung")
        # Mẫu nghề khác — KHÔNG được lộ.
        await _seed_template(db_session, admin_id=uid, profession="graphic-design", name="Mẫu GD")

        resp = await client.get("/api/v1/proposals/term-templates", headers=headers)
        assert resp.status_code == 200, resp.text
        names = {t["name"] for t in resp.json()["data"]}
        assert "Mẫu UX" in names
        assert "Mẫu chung" in names
        assert "Mẫu GD" not in names

    async def test_mau_tat_khong_hien(self, client: AsyncClient, db_session) -> None:
        headers, uid = await _auth_with_profession(client, db_session, "ui-ux-design")
        await _seed_template(
            db_session, admin_id=uid, profession="ui-ux-design", name="Tắt", is_active=False
        )

        resp = await client.get("/api/v1/proposals/term-templates", headers=headers)
        assert all(t["name"] != "Tắt" for t in resp.json()["data"])

    async def test_khac_loai_khong_hien(self, client: AsyncClient, db_session) -> None:
        """Mẫu hợp đồng không lọt vào danh sách mẫu báo giá."""
        headers, uid = await _auth_with_profession(client, db_session, "ui-ux-design")
        await _seed_template(db_session, admin_id=uid, template_type="contract", name="Mẫu HĐ")

        resp = await client.get("/api/v1/proposals/term-templates", headers=headers)
        assert all(t["name"] != "Mẫu HĐ" for t in resp.json()["data"])

    async def test_unauthenticated_401(self, client: AsyncClient) -> None:
        assert (await client.get("/api/v1/proposals/term-templates")).status_code == 401


class TestGenerateWithChosenTemplate:
    async def test_chon_mau_chen_dieu_khoan_nguyen_van(
        self, client: AsyncClient, db_session
    ) -> None:
        headers, uid = await _auth_with_profession(client, db_session, "ui-ux-design")
        body = "Điều khoản UI/UX: bàn giao file nguồn sau thanh toán đủ."
        tid = await _seed_template(db_session, admin_id=uid, profession="ui-ux-design", body=body)
        deal_id = await _make_deal(client, headers)

        resp = await client.post(
            f"/api/v1/proposals/generate-from-deal/{deal_id}?template_id={tid}",
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["data"]["content"]["standard_terms"] == body

    async def test_khong_chon_thi_khong_co_dieu_khoan_chuan(
        self, client: AsyncClient, db_session
    ) -> None:
        headers, uid = await _auth_with_profession(client, db_session, "ui-ux-design")
        await _seed_template(db_session, admin_id=uid, profession="ui-ux-design")
        deal_id = await _make_deal(client, headers)

        resp = await client.post(f"/api/v1/proposals/generate-from-deal/{deal_id}", headers=headers)
        assert resp.status_code == 201
        assert "standard_terms" not in resp.json()["data"]["content"]

    async def test_id_bay_tra_422(self, client: AsyncClient, db_session) -> None:
        headers, _ = await _auth_with_profession(client, db_session, "ui-ux-design")
        deal_id = await _make_deal(client, headers)

        resp = await client.post(
            f"/api/v1/proposals/generate-from-deal/{deal_id}?template_id={uuid.uuid4()}",
            headers=headers,
        )
        assert resp.status_code == 422, resp.text

    async def test_khong_muon_mau_nghe_khac(self, client: AsyncClient, db_session) -> None:
        """Freelancer nghề khác truyền id mẫu ui-ux → coi như không dùng được → 422."""
        headers_ux, uid = await _auth_with_profession(client, db_session, "ui-ux-design")
        tid = await _seed_template(db_session, admin_id=uid, profession="ui-ux-design")

        headers_gd, _ = await _auth_with_profession(client, db_session, "graphic-design")
        deal_id = await _make_deal(client, headers_gd)
        resp = await client.post(
            f"/api/v1/proposals/generate-from-deal/{deal_id}?template_id={tid}",
            headers=headers_gd,
        )
        assert resp.status_code == 422, resp.text
