"""Một bài đi TRỌN chuỗi: admin soạn mẫu → freelancer dựng báo giá → ký hợp đồng → task thu tiền.

Trước bài này chuỗi đó được phủ bởi ba cụm test RỜI NHAU, đứt ở ba mối nối:

  [admin tạo mẫu qua API] ─╳─ [mẫu trong DB]      test khác nhét thẳng bằng `insert()`
  [mẫu → báo giá]          ✓  nhưng dừng ở draft/sent
                           ─╳─
  [accepted → ký → task]   ✓  nhưng báo giá là dict gõ tay, không đến từ mẫu nào

Hệ quả của chỗ đứt: nếu bộ sinh task xử lý sai một `content` kiểu KHUNG thì không bài nào đỏ.
Docstring ở `test_skeleton_no_ai.py` có nói đường khung "vẫn đi qua đúng bộ sinh task thu tiền",
nhưng chưa lần nào thật sự chạy bộ sinh task.

Hai thứ bài này khoá mà không chỗ nào khác khoá được:
  1. Cấu hình CẤU TRÚC của admin (mục đã tắt, tên đầu mục, chữ điều khoản) sống sót qua lượt lưu
     của freelancer — và có mặt đúng/vắng mặt đúng trên bản gửi khách.
  2. Hạng mục chi phí freelancer nhập ra ĐÚNG bấy nhiêu task, đúng số tiền, đúng tên.  #Huynh
"""

import re
import uuid

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import UserModel
from tests.integration.modules.proposals.test_generate_from_deal import _make_deal
from tests.integration.modules.proposals.test_term_templates import _auth_with_profession

# Mẫu admin soạn: phần thân + phần điều khoản, CỘNG ba quyết định về cấu trúc tờ giấy.
NOI_DUNG_MAU = {
    "project_overview": "Dự án thiết kế bộ nhận diện thương hiệu.",
    "scope_of_work": ["Khảo sát và định hướng", "Phác thảo", "Hoàn thiện"],
    "deliverables": ["File nguồn", "Bộ hướng dẫn sử dụng"],
    "timeline": "4 tuần kể từ ngày tạm ứng.",
    "payment_terms": "Tạm ứng 30% khi ký.",
    "standard_terms": "Bàn giao file nguồn sau khi thanh toán đủ.",
    # Ba quyết định CẤU TRÚC — thứ mà tính năng ba tầng sinh ra.
    "hidden_sections": ["assumptions"],
    "section_titles": {"deliverables": "Sản phẩm giao cho khách"},
    # Bộ điều khoản của BÁO GIÁ chỉ có đúng một khoá (`confirmation`) — khác hẳn hợp đồng.
    # Nhét khoá ngoài danh sách vào đây thì allowlist bỏ đi, đúng như thiết kế.
    "clause_texts": {"confirmation": "Đồng ý thì phản hồi email này giúp mình nhé."},
}

HANG_MUC = [
    {"label": "Thiết kế logo", "amount": 8_000_000, "due_type": "on_signing"},
    {"label": "Bộ nhận diện", "amount": 4_000_000, "due_type": "on_completion"},
]
GIA_CHAO = 12_000_000


async def _admin_headers(client: AsyncClient, db_session: AsyncSession) -> dict:
    email = f"admin_{uuid.uuid4().hex[:8]}@example.com"
    password = "Admin@1234!"
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Admin Mẫu"},
    )
    assert reg.status_code == 201, reg.text
    await db_session.execute(update(UserModel).where(UserModel.email == email).values(role="admin"))
    await db_session.flush()
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


async def _tao_mau_qua_api(client: AsyncClient, db_session: AsyncSession) -> str:
    """MỐI NỐI 1: mẫu phải ra đời qua đúng cửa admin dùng, không nhét thẳng vào DB.

    Nhét bằng `insert()` thì schema và validation của `POST /admin/templates` chưa bao giờ được
    chứng minh là sinh ra `content` mà `from-template` tiêu hoá được.
    """
    headers = await _admin_headers(client, db_session)
    resp = await client.post(
        "/api/v1/admin/templates",
        json={
            "name": f"Mẫu nhận diện {uuid.uuid4().hex[:6]}",
            "template_type": "proposal",
            "content": NOI_DUNG_MAU,
            "plan_tier_required": None,
            "is_active": True,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


class TestMauCuaAdminDiToiTaskThuTien:
    async def test_di_tron_chuoi_ra_dung_task(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        mau_id = await _tao_mau_qua_api(client, db_session)
        headers, _ = await _auth_with_profession(client, db_session, "ui-ux-design")
        deal_id = await _make_deal(client, headers, title="Nhận diện thương hiệu")

        # --- Freelancer dựng báo giá TỪ KHUNG, không tốn lượt AI --------------------
        tao = await client.post(
            f"/api/v1/proposals/from-template/{deal_id}?template_id={mau_id}", headers=headers
        )
        assert tao.status_code == 201, tao.text
        pid = tao.json()["data"]["id"]
        noi_dung = tao.json()["data"]["content"]

        assert noi_dung["hidden_sections"] == ["assumptions"]
        assert noi_dung["section_titles"] == {"deliverables": "Sản phẩm giao cho khách"}
        assert noi_dung["clause_texts"] == {
            "confirmation": "Đồng ý thì phản hồi email này giúp mình nhé."
        }
        # Mẫu tuyệt đối không mang tiền — đó là lý do freelancer BẮT BUỘC phải nhập ở dưới.
        for khoa in ("pricing_items", "pricing_detail", "pricing", "payment_milestones"):
            assert khoa not in noi_dung, khoa

        # --- Chốt giá rồi nhập hạng mục -------------------------------------------
        gia = await client.patch(
            f"/api/v1/proposals/{pid}/price", json={"price": GIA_CHAO}, headers=headers
        )
        assert gia.status_code == 200, gia.text

        sau_gia = gia.json()["data"]["content"]
        sau_gia["pricing_items"] = HANG_MUC
        luu = await client.patch(
            f"/api/v1/proposals/{pid}",
            json={"deal_id": deal_id, "content": sau_gia},
            headers=headers,
        )
        assert luu.status_code == 200, luu.text

        # Lượt lưu KHÔNG được nuốt cấu hình của admin. `PATCH` thay TOÀN BỘ content, nên đây là
        # chỗ khoá lại cái bẫy đã cắn sáu lần ở màn soạn báo giá.
        da_luu = luu.json()["data"]["content"]
        assert da_luu["hidden_sections"] == ["assumptions"]
        assert da_luu["section_titles"] == {"deliverables": "Sản phẩm giao cho khách"}
        assert da_luu["clause_texts"] == {
            "confirmation": "Đồng ý thì phản hồi email này giúp mình nhé."
        }

        # --- Gửi → khách chấp nhận → ký hợp đồng -----------------------------------
        for trang_thai in ("sent", "accepted"):
            r = await client.patch(
                f"/api/v1/proposals/{pid}/status", json={"status": trang_thai}, headers=headers
            )
            assert r.status_code == 200, r.text

        deal = (await client.get(f"/api/v1/deals/{deal_id}", headers=headers)).json()["data"]
        hd = await client.post(
            "/api/v1/contracts",
            json={
                "deal_id": deal_id,
                "proposal_id": pid,
                "client_id": deal["client_id"],
                "content": {},
            },
            headers=headers,
        )
        assert hd.status_code == 201, hd.text
        hd_id = hd.json()["data"]["id"]

        for trang_thai in ("pending_signatures", "active"):
            r = await client.patch(
                f"/api/v1/contracts/{hd_id}/status", json={"status": trang_thai}, headers=headers
            )
            assert r.status_code == 200, r.text

        # --- MỐI NỐI 2: hạng mục chi phí ra đúng bấy nhiêu task --------------------
        du_an = (await client.get("/api/v1/projects", headers=headers)).json()["data"]
        du_an_id = next(p["id"] for p in du_an if p["deal_id"] == deal_id)
        task = (
            await client.get(f"/api/v1/projects/{du_an_id}/tasks", headers=headers)
        ).json()["data"]

        # Nhận biết bằng `billing_amount`, KHÔNG bằng tiền tố trong tên: tên task là nhãn hạng
        # mục nguyên văn do freelancer đặt.
        thu_tien = [t for t in task if t.get("billing_amount")]
        assert len(thu_tien) == len(HANG_MUC), [t["title"] for t in task]
        assert [t["title"] for t in thu_tien] == [m["label"] for m in HANG_MUC]
        assert [int(float(t["billing_amount"])) for t in thu_tien] == [
            m["amount"] for m in HANG_MUC
        ]
        assert sum(int(float(t["billing_amount"])) for t in thu_tien) == GIA_CHAO

    async def test_cau_hinh_cua_admin_hien_dung_tren_ban_gui_khach(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Ba quyết định của admin phải đi hết đường tới tờ giấy khách đọc.

        Tách khỏi bài trên vì hỏng ở đây là hỏng thứ khác hẳn: chuỗi tiền vẫn chạy đúng mà tờ
        giấy vẫn sai.
        """
        mau_id = await _tao_mau_qua_api(client, db_session)
        headers, _ = await _auth_with_profession(client, db_session, "ui-ux-design")
        deal_id = await _make_deal(client, headers)

        tao = await client.post(
            f"/api/v1/proposals/from-template/{deal_id}?template_id={mau_id}", headers=headers
        )
        pid = tao.json()["data"]["id"]

        xem = await client.get(f"/api/v1/proposals/{pid}/preview", headers=headers)
        assert xem.status_code == 200, xem.text
        giay = xem.json()["data"]["html"]

        # Mục admin TẮT không được có mặt; mục admin ĐỔI TÊN phải mang tên mới.
        assert "Ghi Chú" not in giay
        assert "Sản phẩm giao cho khách" in giay
        assert "Sản Phẩm Bàn Giao" not in giay
        # Chữ điều khoản admin gõ đè lên chữ mặc định.
        assert "Đồng ý thì phản hồi email này giúp mình nhé." in giay

        # Tắt một mục KHÔNG được làm đứt số thứ tự — khách đọc tưởng bị cắt mất trang.
        so = [int(x) for x in re.findall(r"<h2[^>]*>(\d+)\.", giay)]
        assert so == list(range(1, len(so) + 1)), so
