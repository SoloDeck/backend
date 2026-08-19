"""Soạn hợp đồng từ KHUNG mẫu — không dùng AI.

Bên hợp đồng trước bản này còn bí hơn báo giá: báo giá ít nhất có một lối rơi khi AI lỗi, còn
hợp đồng thì mọi nút đều bắn AI và 402 là hết đường. Freelancer gói Free đứng ở bước thương
lượng không đi tiếp được.  #Huynh
"""

import uuid

from httpx import AsyncClient
from sqlalchemy import insert

from src.infrastructure.database.models import SystemTemplateModel
from src.main import app
from src.shared.dependencies.ai import get_ai_facade
from tests.integration.modules.contracts.test_contracts_api import (
    _auth,
    _create_accepted_proposal,
    _create_client,
    _create_contract,
    _create_deal,
)
from tests.integration.modules.proposals.test_generate_from_deal import _PermissiveAIFacade

KHUNG_HOP_DONG = {
    "scope_of_work": "Thiết kế và bàn giao bộ nhận diện thương hiệu theo phụ lục đính kèm.",
    "payment_terms": "Tạm ứng 30% khi ký, thanh toán phần còn lại trong 7 ngày sau nghiệm thu.",
    "ip_ownership": "Toàn bộ quyền sở hữu trí tuệ chuyển cho Bên B sau khi thanh toán đủ.",
    "termination_clause": "Mỗi Bên được đơn phương chấm dứt sau khi báo trước 15 ngày.",
    "standard_terms": "Bàn giao file nguồn cùng sản phẩm cuối.",
    "custom_clauses": "Bên A được dùng sản phẩm trong hồ sơ năng lực.",
}


async def _seed(db_session, *, admin_id: str, content: dict, is_active: bool = True) -> str:
    tid = uuid.uuid4()
    await db_session.execute(
        insert(SystemTemplateModel).values(
            id=tid,
            template_type="contract",
            name="Khung hợp đồng",
            profession=None,
            content=content,
            is_active=is_active,
            version_number=1,
            created_by_admin_id=uuid.UUID(admin_id),
        )
    )
    await db_session.flush()
    return str(tid)


async def _draft_contract(http: AsyncClient, headers: dict) -> str:
    client_id = await _create_client(http, headers)
    deal_id = await _create_deal(http, headers, client_id)
    proposal_id = await _create_accepted_proposal(http, headers, deal_id)
    return await _create_contract(http, headers, deal_id, proposal_id, client_id)


async def _user_id(http: AsyncClient, headers: dict) -> str:
    me = await http.get("/api/v1/users/me", headers=headers)
    return me.json()["data"]["id"]


class TestSoanHopDongTuKhung:
    async def test_khung_dien_dung_cac_dieu_can_freelancer_tu_viet(
        self, client: AsyncClient, db_session
    ) -> None:
        headers = await _auth(client)
        tid = await _seed(
            db_session, admin_id=await _user_id(client, headers), content=KHUNG_HOP_DONG
        )
        cid = await _draft_contract(client, headers)

        resp = await client.post(
            f"/api/v1/contracts/{cid}/from-template?template_id={tid}", headers=headers
        )
        assert resp.status_code == 200, resp.text
        content = resp.json()["data"]["content"]
        # Điều 1 và Điều 3 là hai chỗ trống nặng nhất của tờ hợp đồng: bộ khoá chế độ AI cố ý
        # không chạm tới, nên nếu khung cũng không với tới thì đường không-AI vô dụng.
        assert content["scope_of_work"] == KHUNG_HOP_DONG["scope_of_work"]
        assert content["payment_terms"] == KHUNG_HOP_DONG["payment_terms"]
        assert content["ip_ownership"] == KHUNG_HOP_DONG["ip_ownership"]
        assert content["termination_clause"] == KHUNG_HOP_DONG["termination_clause"]
        assert content["custom_clauses"] == KHUNG_HOP_DONG["custom_clauses"]

    async def test_khung_trang_van_ra_ban_nhap_hop_le(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _draft_contract(client, headers)

        resp = await client.post(f"/api/v1/contracts/{cid}/from-template", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["content"] == {}

    async def test_cung_mot_user_ai_chan_402_nhung_khung_di_lot(
        self, client: AsyncClient
    ) -> None:
        """Đối chứng trực tiếp, trên đúng một tài khoản.

        `_auth` không cấp gói AI — đúng cảnh gói Free. Bài này chốt rằng đường khung không phải
        "tình cờ chạy được" mà là lối đi duy nhất còn mở cho họ.

        Vẫn phải cắm AI giả: cổng 402 nằm TRONG service, sau khi FastAPI đã dựng xong
        dependency — không có stub thì hỏng ở `GROQ_API_KEY` trước khi tới cổng.
        """
        app.dependency_overrides[get_ai_facade] = lambda: _PermissiveAIFacade()
        try:
            await self._ai_chan_khung_lot(client)
        finally:
            app.dependency_overrides.pop(get_ai_facade, None)

    async def _ai_chan_khung_lot(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _draft_contract(client, headers)

        ai = await client.post(f"/api/v1/contracts/{cid}/generate", headers=headers)
        assert ai.status_code == 402, ai.text

        khung = await client.post(f"/api/v1/contracts/{cid}/from-template", headers=headers)
        assert khung.status_code == 200, khung.text

    async def test_mau_bay_thi_chan(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _draft_contract(client, headers)

        resp = await client.post(
            f"/api/v1/contracts/{cid}/from-template?template_id={uuid.uuid4()}", headers=headers
        )
        assert resp.status_code == 422, resp.text

    async def test_hop_dong_da_gui_thi_khong_dien_de_len(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _draft_contract(client, headers)
        await client.post(f"/api/v1/contracts/{cid}/send", headers=headers)

        resp = await client.post(f"/api/v1/contracts/{cid}/from-template", headers=headers)
        assert resp.status_code == 409, resp.text


class TestOTrongCuaHopDong:
    async def test_editable_render_ca_dieu_dang_trong(self, client: AsyncClient) -> None:
        """Cờ `editable` từng là cờ CHẾT.

        `render.py` hứa "render cả điều khoản đang trống thành ô rỗng", router có query param,
        FE có truyền — nhưng `contract.html` không hề tham chiếu biến đó. Nó rơi vào hư không.
        """
        headers = await _auth(client)
        cid = await _draft_contract(client, headers)
        await client.post(f"/api/v1/contracts/{cid}/from-template", headers=headers)

        resp = await client.get(
            f"/api/v1/contracts/{cid}/preview?editable=true", headers=headers
        )
        assert resp.status_code == 200, resp.text
        html = resp.json()["data"]["html"]

        for field in ("revision_policy", "standard_terms", "custom_clauses"):
            assert f'data-field="{field}"' in html, field

    async def test_ban_khach_ky_khong_co_o_rong(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _draft_contract(client, headers)
        await client.post(f"/api/v1/contracts/{cid}/from-template", headers=headers)

        resp = await client.get(f"/api/v1/contracts/{cid}/preview", headers=headers)
        html = resp.json()["data"]["html"]

        for field in ("revision_policy", "standard_terms", "custom_clauses"):
            assert f'data-field="{field}"' not in html, field

    async def test_so_dieu_van_lien_mach_o_che_do_sua(self, client: AsyncClient) -> None:
        import re

        headers = await _auth(client)
        cid = await _draft_contract(client, headers)
        await client.post(f"/api/v1/contracts/{cid}/from-template", headers=headers)

        resp = await client.get(
            f"/api/v1/contracts/{cid}/preview?editable=true", headers=headers
        )
        html = resp.json()["data"]["html"]

        so_dieu = [int(n) for n in re.findall(r"<h2>Điều (\d+)\.", html)]
        assert so_dieu == list(range(1, len(so_dieu) + 1)), so_dieu
