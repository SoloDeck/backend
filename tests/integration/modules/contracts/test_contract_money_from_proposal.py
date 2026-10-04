"""Hợp đồng phải mang ĐÚNG tiền và phạm vi của báo giá đã chốt — cả đường không AI lẫn có AI.

Hai chỗ lệch đo được khi thử trọn flow báo giá -> hợp đồng -> ký:

- Đường KHÔNG AI: hợp đồng chỉ lấy chữ từ mẫu, Điều 3 không có tổng giá trị lẫn lịch thanh toán.
- Đường CÓ AI: model tự viết lại các đợt thanh toán nên số từng đợt lệch bảng hạng mục của báo giá,
  trong khi task thu tiền và hoá đơn bám đúng báo giá.

Bất biến cần giữ: bảng lịch thanh toán trong hợp đồng, bảng hạng mục của báo giá và các task thu
tiền sinh ra sau khi ký là CÙNG MỘT danh sách.  #Huynh
"""

import uuid

from httpx import AsyncClient
from sqlalchemy import select

from src.infrastructure.database.models import ProjectModel, TaskModel
from src.main import app
from src.shared.dependencies.ai import get_ai_facade
from tests.conftest import grant_ai_plan
from tests.integration.modules.contracts.test_contract_skeleton_no_ai import _seed, _user_id
from tests.integration.modules.contracts.test_contracts_api import (
    _auth,
    _create_client,
    _create_contract,
    _create_deal,
)

HANG_MUC = [
    {"label": "Khảo sát và wireframe", "amount": 3_600_000, "due_type": "on_signing"},
    {"label": "Thiết kế giao diện (UI)", "amount": 4_800_000},
    {"label": "Bàn giao file và hướng dẫn", "amount": 3_600_000},
]

NOI_DUNG_BAO_GIA = {
    "pricing": {"total": 12_000_000, "currency": "VND"},
    "pricing_items": HANG_MUC,
    "scope_of_work": ["Khảo sát yêu cầu", "Thiết kế luồng người dùng", "Thiết kế giao diện"],
    "deliverables": ["File thiết kế Figma", "Bộ UI kit"],
    "out_of_scope": ["Lập trình giao diện", "Chi phí in ấn"],
}

MAU_HOP_DONG = {
    "scope_of_work": "Thiết kế giao diện theo phạm vi trong báo giá đã duyệt.",
    "payment_terms": "Mỗi hạng mục thanh toán trong 7 ngày kể từ ngày đến hạn.",
    "ip_ownership": "Quyền sở hữu trí tuệ chuyển cho Bên B sau khi thanh toán đủ.",
}

SO_TIEN_HIEN_THI = ["3.600.000 VND", "4.800.000 VND", "3.600.000 VND"]


async def _bao_gia_da_chot(http: AsyncClient, headers: dict, deal_id: str) -> str:
    resp = await http.post(
        "/api/v1/proposals",
        json={"deal_id": deal_id, "content": NOI_DUNG_BAO_GIA},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    pid = resp.json()["data"]["id"]
    for status in ("sent", "accepted"):
        r = await http.patch(
            f"/api/v1/proposals/{pid}/status", json={"status": status}, headers=headers
        )
        assert r.status_code == 200, r.text
    return pid


async def _hop_dong_nhap(http: AsyncClient, headers: dict) -> tuple[str, str]:
    """Trả (contract_id, deal_id) của một hợp đồng nháp từ báo giá đã chốt có đủ hạng mục."""
    client_id = await _create_client(http, headers)
    deal_id = await _create_deal(http, headers, client_id)
    proposal_id = await _bao_gia_da_chot(http, headers, deal_id)
    return await _create_contract(http, headers, deal_id, proposal_id, client_id), deal_id


async def _xem_truoc(http: AsyncClient, headers: dict, contract_id: str) -> str:
    resp = await http.get(f"/api/v1/contracts/{contract_id}/preview", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["html"]


async def _dieu_3(html: str) -> str:
    """Cắt đúng đoạn Điều 3 (Giá trị hợp đồng) khỏi tờ giấy để không khớp nhầm chỗ khác."""
    start = html.index("Giá Trị Hợp Đồng")
    end = html.index("Quyền và Nghĩa Vụ Của Bên A", start)
    return html[start:end]


class TestKhongAiLayTienVaPhamViTuBaoGia:
    async def test_dieu_3_co_tong_gia_tri_bang_so_bang_chu_va_bang_cac_dot(
        self, client: AsyncClient, db_session
    ) -> None:
        headers = await _auth(client)
        tid = await _seed(
            db_session, admin_id=await _user_id(client, headers), content=MAU_HOP_DONG
        )
        cid, _ = await _hop_dong_nhap(client, headers)

        resp = await client.post(
            f"/api/v1/contracts/{cid}/from-template?template_id={tid}", headers=headers
        )
        assert resp.status_code == 200, resp.text
        html = await _xem_truoc(client, headers, cid)
        dieu_3 = await _dieu_3(html)

        assert "Tổng giá trị hợp đồng là 12.000.000 VND (Mười hai triệu đồng Việt Nam)" in dieu_3
        # Lời admin viết trong mẫu vẫn còn, nằm SAU câu về tiền.
        assert MAU_HOP_DONG["payment_terms"] in dieu_3
        cau_ve_tien = dieu_3.index("Tổng giá trị hợp đồng là")
        assert cau_ve_tien < dieu_3.index(MAU_HOP_DONG["payment_terms"])
        assert 'class="schedule"' in dieu_3
        for hang_muc, so_tien in zip(HANG_MUC, SO_TIEN_HIEN_THI, strict=True):
            assert hang_muc["label"] in dieu_3
            assert so_tien in dieu_3
        assert "Khi ký hợp đồng" in dieu_3
        assert "Khi hoàn thành hạng mục" in dieu_3
        assert "12.000.000 VND" in dieu_3.split("<tfoot>")[1]

    async def test_dieu_1_co_phan_viec_san_pham_va_ngoai_pham_vi_cua_bao_gia(
        self, client: AsyncClient, db_session
    ) -> None:
        headers = await _auth(client)
        tid = await _seed(
            db_session, admin_id=await _user_id(client, headers), content=MAU_HOP_DONG
        )
        cid, _ = await _hop_dong_nhap(client, headers)

        resp = await client.post(
            f"/api/v1/contracts/{cid}/from-template?template_id={tid}", headers=headers
        )

        scope = resp.json()["data"]["content"]["scope_of_work"]
        assert scope.startswith(MAU_HOP_DONG["scope_of_work"])
        assert "1. Phạm vi công việc:\n- Khảo sát yêu cầu\n- Thiết kế luồng người dùng" in scope
        assert "2. Sản phẩm bàn giao:\n- File thiết kế Figma\n- Bộ UI kit" in scope
        assert "3. Phạm vi không bao gồm:\n- Lập trình giao diện\n- Chi phí in ấn" in scope

    async def test_khung_trang_khong_mau_van_co_tien_va_pham_vi(
        self, client: AsyncClient
    ) -> None:
        headers = await _auth(client)
        cid, _ = await _hop_dong_nhap(client, headers)

        resp = await client.post(f"/api/v1/contracts/{cid}/from-template", headers=headers)

        content = resp.json()["data"]["content"]
        assert content["payment_terms"].startswith("Tổng giá trị hợp đồng là 12.000.000 VND")
        assert content["scope_of_work"].startswith("1. Phạm vi công việc:")
        dieu_3 = await _dieu_3(await _xem_truoc(client, headers, cid))
        assert 'class="schedule"' in dieu_3
        assert "Bàn giao file và hướng dẫn" in dieu_3

    async def test_dot_thanh_toan_nguoi_dung_tu_them_duoc_uu_tien_hon_bang_suy_tu_bao_gia(
        self, client: AsyncClient
    ) -> None:
        headers = await _auth(client)
        cid, _ = await _hop_dong_nhap(client, headers)
        await client.post(f"/api/v1/contracts/{cid}/from-template", headers=headers)
        added = await client.post(
            f"/api/v1/contracts/{cid}/milestones",
            json={"description": "Đợt tự thêm", "amount": "7000000"},
            headers=headers,
        )
        assert added.status_code == 201, added.text

        dieu_3 = await _dieu_3(await _xem_truoc(client, headers, cid))

        assert "Đợt tự thêm" in dieu_3
        assert "7.000.000 VND" in dieu_3
        # Đã có đợt do người dùng nhập thì KHÔNG trộn thêm dòng suy từ báo giá.
        assert "Khảo sát và wireframe" not in dieu_3

    async def test_ban_xem_truoc_va_ban_gui_di_cung_mot_bang(
        self, client: AsyncClient
    ) -> None:
        """Preview là đúng thứ PDF sẽ in (cùng `_build_document`): bảng không được khác nhau."""
        headers = await _auth(client)
        cid, _ = await _hop_dong_nhap(client, headers)
        await client.post(f"/api/v1/contracts/{cid}/from-template", headers=headers)

        thuong = await _dieu_3(await _xem_truoc(client, headers, cid))
        resp = await client.get(
            f"/api/v1/contracts/{cid}/preview", params={"editable": True}, headers=headers
        )
        sua_duoc = await _dieu_3(resp.json()["data"]["html"])

        for so_tien in SO_TIEN_HIEN_THI:
            assert so_tien in thuong
            assert so_tien in sua_duoc

    async def test_bang_trong_hop_dong_trung_khop_task_thu_tien_sau_khi_ky(
        self, client: AsyncClient, db_session
    ) -> None:
        """Gốc của lỗi: hợp đồng, báo giá và hoá đơn phải là CÙNG MỘT danh sách tiền."""
        headers = await _auth(client)
        cid, deal_id = await _hop_dong_nhap(client, headers)
        await client.post(f"/api/v1/contracts/{cid}/from-template", headers=headers)
        sent = await client.post(f"/api/v1/contracts/{cid}/send", headers=headers)
        assert sent.status_code == 200, sent.text
        token = sent.json()["data"]["share_token"]
        freelancer_ky = await client.post(f"/api/v1/contracts/{cid}/sign", headers=headers)
        assert freelancer_ky.status_code == 200, freelancer_ky.text
        signed = await client.post(
            f"/api/v1/contracts/public/{token}/sign", json={"signer_name": "Khách"}
        )
        assert signed.status_code == 200, signed.text

        rows = await db_session.execute(
            select(TaskModel.title, TaskModel.billing_amount).where(
                TaskModel.entity_type == "project",
                TaskModel.entity_id.in_(
                    select(ProjectModel.id).where(ProjectModel.deal_id == uuid.UUID(deal_id))
                ),
            )
        )
        tasks = sorted((title, int(amount)) for title, amount in rows)
        bang = sorted((h["label"], h["amount"]) for h in HANG_MUC)

        assert tasks == bang
        dieu_3 = await _dieu_3(await _xem_truoc(client, headers, cid))
        for label, amount in bang:
            assert label in dieu_3
            assert f"{amount:,}".replace(",", ".") + " VND" in dieu_3


class _AiHopDongBiaSo:
    """AI giả viết một lịch thanh toán KHÁC báo giá — đúng lỗi đã đo được với Gemini."""

    async def generate_contract(self, **_: object) -> dict:
        return {
            "scope_of_work": "Phạm vi do AI viết, giữ nguyên.",
            "payment_terms": (
                "Tổng giá trị 12.000.000 ₫. Hạng mục 1: 2.400.000 ₫. Hạng mục 2: 3.600.000 ₫. "
                "Hạng mục 3: 4.800.000 ₫. Hạng mục 4: 1.200.000 ₫."
            ),
            "revision_policy": "Hai vòng chỉnh sửa miễn phí.",
            "ip_ownership": "Chuyển giao sau khi thanh toán đủ.",
            "termination_clause": "Báo trước 15 ngày.",
            "custom_clauses": "",
            "parties": {"freelancer": {}, "client": {}},
            "governing_law": "Vietnam",
        }

    def last_usage(self, module: str) -> None:
        return None


class TestCoAiKhongLechBaoGia:
    async def _tao_voi_ai_gia(self, client: AsyncClient, db_session, headers: dict) -> str:
        me = await client.get("/api/v1/users/me", headers=headers)
        await grant_ai_plan(db_session, uuid.UUID(me.json()["data"]["id"]))
        cid, _ = await _hop_dong_nhap(client, headers)
        app.dependency_overrides[get_ai_facade] = lambda: _AiHopDongBiaSo()
        try:
            resp = await client.post(f"/api/v1/contracts/{cid}/generate", headers=headers)
        finally:
            app.dependency_overrides.pop(get_ai_facade, None)
        assert resp.status_code == 200, resp.text
        return cid

    async def test_so_tien_model_tu_viet_bi_bo_di_chi_con_so_cua_bao_gia(
        self, client: AsyncClient, db_session
    ) -> None:
        headers = await _auth(client)
        cid = await self._tao_voi_ai_gia(client, db_session, headers)

        content = (await client.get(f"/api/v1/contracts/{cid}", headers=headers)).json()["data"][
            "content"
        ]

        assert "2.400.000" not in content["payment_terms"]
        assert "1.200.000" not in content["payment_terms"]
        assert content["payment_terms"].startswith(
            "Tổng giá trị hợp đồng là 12.000.000 VND (Mười hai triệu đồng Việt Nam)."
        )

    async def test_bang_cac_dot_khop_bao_gia_tung_dong(
        self, client: AsyncClient, db_session
    ) -> None:
        headers = await _auth(client)
        cid = await self._tao_voi_ai_gia(client, db_session, headers)

        dieu_3 = await _dieu_3(await _xem_truoc(client, headers, cid))

        for hang_muc, so_tien in zip(HANG_MUC, SO_TIEN_HIEN_THI, strict=True):
            assert hang_muc["label"] in dieu_3
            assert so_tien in dieu_3
        assert "2.400.000" not in dieu_3
        assert "1.200.000" not in dieu_3

    async def test_phan_van_xuoi_cua_model_van_giu(
        self, client: AsyncClient, db_session
    ) -> None:
        headers = await _auth(client)
        cid = await self._tao_voi_ai_gia(client, db_session, headers)

        content = (await client.get(f"/api/v1/contracts/{cid}", headers=headers)).json()["data"][
            "content"
        ]

        assert content["scope_of_work"] == "Phạm vi do AI viết, giữ nguyên."
        assert content["revision_policy"] == "Hai vòng chỉnh sửa miễn phí."
        assert content["ip_ownership"] == "Chuyển giao sau khi thanh toán đủ."
        assert content["termination_clause"] == "Báo trước 15 ngày."

    async def test_hai_duong_cho_cung_mot_bang_tien(
        self, client: AsyncClient, db_session
    ) -> None:
        """Cùng một báo giá: bảng tiền của đường AI và đường không AI phải giống hệt nhau."""
        headers = await _auth(client)
        cid_ai = await self._tao_voi_ai_gia(client, db_session, headers)
        cid_khung, _ = await _hop_dong_nhap(client, headers)
        await client.post(f"/api/v1/contracts/{cid_khung}/from-template", headers=headers)

        bang_ai = (await _dieu_3(await _xem_truoc(client, headers, cid_ai))).split("<table")[1]
        bang_khung = (await _dieu_3(await _xem_truoc(client, headers, cid_khung))).split(
            "<table"
        )[1]

        assert bang_ai == bang_khung
