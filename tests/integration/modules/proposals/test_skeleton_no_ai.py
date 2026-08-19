"""Đường soạn tài liệu KHÔNG dùng AI, chạy hết từ API thật.

Trước bản này, thư viện mẫu chỉ với được từ trong bụng hai hàm `generate_*` — muốn dùng mẫu là
bắt buộc tiêu một lượt AI, dù `build_skeleton_content` không cần LLM một chút nào. Freelancer
gói Free do đó không có cách nào tạo ra một tờ báo giá hay hợp đồng, kể cả khi chấp nhận tự gõ
toàn bộ.

Bốn thứ khoá ở đây: khung với tới được phần đặc thù dự án, KHÔNG tốn lượt AI, gói Free đi lọt,
và bất biến tiền không lỏng ra một chút nào so với chế độ AI.  #Huynh
"""

import re
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import insert, select

from src.infrastructure.database.models import (
    SystemTemplateModel,
    UsageRecordModel,
)
from src.main import app
from src.shared.dependencies.ai import get_ai_facade
from tests.integration.modules.proposals.test_generate_from_deal import (
    _make_deal,
    _PermissiveAIFacade,
)
from tests.integration.modules.proposals.test_term_templates import _auth_with_profession

KHUNG_BAO_GIA = {
    "project_overview": "Dự án thiết kế bộ nhận diện thương hiệu.",
    "scope_of_work": ["Khảo sát và định hướng", "Phác thảo", "Hoàn thiện và bàn giao"],
    "deliverables": ["File nguồn", "Bộ hướng dẫn sử dụng"],
    "timeline": "4 tuần kể từ ngày tạm ứng.",
    "payment_terms": "Tạm ứng 30% khi ký, thanh toán phần còn lại khi bàn giao.",
    "out_of_scope": ["Mua font bản quyền", "Chi phí in ấn"],
    "revision_policy": "2 vòng chỉnh sửa miễn phí cho mỗi hạng mục.",
    "standard_terms": "Bàn giao file nguồn sau khi thanh toán đủ.",
}


async def _seed(
    db_session,
    *,
    admin_id: str,
    content: dict,
    template_type: str = "proposal",
    profession: str | None = None,
    name: str = "Mẫu có khung",
    is_active: bool = True,
) -> str:
    tid = uuid.uuid4()
    await db_session.execute(
        insert(SystemTemplateModel).values(
            id=tid,
            template_type=template_type,
            name=name,
            profession=profession,
            content=content,
            is_active=is_active,
            version_number=1,
            created_by_admin_id=uuid.UUID(admin_id),
        )
    )
    await db_session.flush()
    return str(tid)


async def _register_free(client: AsyncClient) -> tuple[dict, str]:
    """User đăng ký mới, KHÔNG cấp gói AI — đúng cảnh gói Free đang gặp."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"free_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Test@1234!",
            "full_name": "Free User",
        },
    )
    headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    me = await client.get("/api/v1/users/me", headers=headers)
    return headers, me.json()["data"]["id"]


async def _luot_ai_da_dung(db_session, user_id: str) -> int:
    rows = await db_session.execute(
        select(UsageRecordModel.ai_generations_used).where(
            UsageRecordModel.user_id == uuid.UUID(user_id)
        )
    )
    return sum(rows.scalars().all())


class TestSoanBaoGiaTuKhung:
    async def test_khung_dien_ca_phan_dac_thu_du_an(
        self, client: AsyncClient, db_session
    ) -> None:
        headers, uid = await _auth_with_profession(client, db_session, "ui-ux-design")
        tid = await _seed(db_session, admin_id=uid, content=KHUNG_BAO_GIA)
        deal_id = await _make_deal(client, headers)

        resp = await client.post(
            f"/api/v1/proposals/from-template/{deal_id}?template_id={tid}", headers=headers
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]

        assert data["status"] == "draft"
        assert data["ai_generated"] is False

        content = data["content"]
        # Đây là khác biệt cốt lõi với chế độ AI: mẫu với được tới mục 3-6, vì không còn AI nào
        # viết hộ. Thiếu chỗ này thì tờ giấy chỉ có điều khoản mà không có nội dung.
        assert content["project_overview"] == KHUNG_BAO_GIA["project_overview"]
        assert content["scope_of_work"] == KHUNG_BAO_GIA["scope_of_work"]
        assert content["deliverables"] == KHUNG_BAO_GIA["deliverables"]
        assert content["timeline"] == KHUNG_BAO_GIA["timeline"]
        assert content["payment_terms"] == KHUNG_BAO_GIA["payment_terms"]
        assert content["out_of_scope"] == KHUNG_BAO_GIA["out_of_scope"]
        assert content["standard_terms"] == KHUNG_BAO_GIA["standard_terms"]

    async def test_khong_ton_mot_luot_ai_nao(self, client: AsyncClient, db_session) -> None:
        """Bài test mang cả ý nghĩa nghiệp vụ, không chỉ kỹ thuật.

        Cả lý do endpoint này tồn tại nằm ở đây: dùng được thư viện mẫu mà không phải trả bằng
        một lượt gọi model.
        """
        headers, uid = await _auth_with_profession(client, db_session, "ui-ux-design")
        tid = await _seed(db_session, admin_id=uid, content=KHUNG_BAO_GIA)
        deal_id = await _make_deal(client, headers)

        truoc = await _luot_ai_da_dung(db_session, uid)
        resp = await client.post(
            f"/api/v1/proposals/from-template/{deal_id}?template_id={tid}", headers=headers
        )
        assert resp.status_code == 201, resp.text
        assert await _luot_ai_da_dung(db_session, uid) == truoc

    async def test_khung_trang_khong_can_mau_nao(
        self, client: AsyncClient, db_session
    ) -> None:
        # `template_id` để trống là HỢP LỆ: tờ giấy trống với đủ ô để tự điền. Đây là lối đi
        # luôn dùng được, kể cả khi admin chưa soạn mẫu nào.
        headers, _ = await _auth_with_profession(client, db_session, "ui-ux-design")
        deal_id = await _make_deal(client, headers)

        resp = await client.post(
            f"/api/v1/proposals/from-template/{deal_id}", headers=headers
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["data"]["content"] == {}

    async def test_mau_chua_soan_khung_thi_ra_ban_nhap_rong(
        self, client: AsyncClient, db_session
    ) -> None:
        # Mẫu chỉ có khối điều khoản (kiểu cũ) vẫn chọn được ở tab khung — ra đúng phần nó có.
        headers, uid = await _auth_with_profession(client, db_session, "ui-ux-design")
        tid = await _seed(db_session, admin_id=uid, content={"body": "Điều khoản kiểu cũ"})
        deal_id = await _make_deal(client, headers)

        resp = await client.post(
            f"/api/v1/proposals/from-template/{deal_id}?template_id={tid}", headers=headers
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["data"]["content"] == {"standard_terms": "Điều khoản kiểu cũ"}

    async def test_mau_bay_thi_chan_chu_khong_im_lang_bo_qua(
        self, client: AsyncClient, db_session
    ) -> None:
        headers, _ = await _auth_with_profession(client, db_session, "ui-ux-design")
        deal_id = await _make_deal(client, headers)

        resp = await client.post(
            f"/api/v1/proposals/from-template/{deal_id}?template_id={uuid.uuid4()}",
            headers=headers,
        )
        assert resp.status_code == 422, resp.text

    async def test_khung_tuyet_doi_khong_cham_tien(
        self, client: AsyncClient, db_session
    ) -> None:
        """Bất biến tiền áp cho CẢ HAI chế độ, không lỏng ra ở đường không-AI.

        Báo giá soạn từ khung vẫn đi qua đúng cổng gửi và đúng bộ sinh task thu tiền, nên một
        mẫu DÙNG CHUNG ghi đè được tiền là phá "tổng hạng mục = giá chào khách" từ bên ngoài.
        """
        headers, uid = await _auth_with_profession(client, db_session, "ui-ux-design")
        tid = await _seed(
            db_session,
            admin_id=uid,
            content={
                "standard_terms": "Điều khoản thật",
                "pricing_items": [{"label": "Mẫu chèn bậy", "amount": 1}],
                "pricing_detail": {"final_price": 1},
                "payment_milestones": [{"percent": 100}],
            },
        )
        deal_id = await _make_deal(client, headers)

        resp = await client.post(
            f"/api/v1/proposals/from-template/{deal_id}?template_id={tid}", headers=headers
        )
        content = resp.json()["data"]["content"]
        assert content == {"standard_terms": "Điều khoản thật"}


class TestGoiFreeVanRaDuocTaiLieu:
    """Trước bản này gói Free là ngõ cụt: mọi nút tạo đều bắn AI và ăn 402."""

    @pytest.fixture(autouse=True)
    def _permissive_ai(self):
        app.dependency_overrides[get_ai_facade] = lambda: _PermissiveAIFacade()
        yield
        app.dependency_overrides.pop(get_ai_facade, None)

    async def test_duong_ai_van_chan_402(self, client: AsyncClient) -> None:
        # Kiểm chứng cái nền: user này THẬT SỰ không dùng được AI. Không có bài này thì bài
        # dưới có thể xanh chỉ vì user vô tình có gói.
        headers, _ = await _register_free(client)
        deal_id = await _make_deal(client, headers)

        resp = await client.post(
            f"/api/v1/proposals/generate-from-deal/{deal_id}", headers=headers
        )
        assert resp.status_code == 402, resp.text

    async def test_duong_khung_di_lot(self, client: AsyncClient) -> None:
        headers, _ = await _register_free(client)
        deal_id = await _make_deal(client, headers)

        resp = await client.post(
            f"/api/v1/proposals/from-template/{deal_id}", headers=headers
        )
        assert resp.status_code == 201, resp.text

    async def test_chot_gia_thoi_chua_du_de_gui_phai_co_hang_muc(
        self, client: AsyncClient
    ) -> None:
        """Đường khung mở bảng hạng mục TRỐNG, nên đây là ngã rẽ mặc định của gói Free.

        Mẫu tuyệt đối không mang tiền, mà `PATCH /price` chỉ đặt TỔNG. Nếu cổng gửi chỉ đòi
        "một con số > 0" thì báo giá trắng hạng mục đi lọt, và cuối đường bộ sinh task rơi
        xuống nhánh chia mốc % — freelancer nhận hai task chung chung thay vì một task cho mỗi
        hạng mục, mà không được báo gì.  #Huynh
        """
        headers, _ = await _register_free(client)
        deal_id = await _make_deal(client, headers)

        tao = await client.post(f"/api/v1/proposals/from-template/{deal_id}", headers=headers)
        pid = tao.json()["data"]["id"]

        gia = await client.patch(
            f"/api/v1/proposals/{pid}/price", json={"price": 12_000_000}, headers=headers
        )
        assert gia.status_code == 200, gia.text

        gui = await client.patch(
            f"/api/v1/proposals/{pid}/status", json={"status": "sent"}, headers=headers
        )
        assert gui.status_code == 409, gui.text
        # Câu của ĐÚNG cổng này — cổng "tổng lệch giá chào" cũng nhắc "hạng mục chi phí".
        assert "Chưa có hạng mục chi phí nào" in gui.json()["error"]["message"]

    async def test_free_di_duoc_toi_het_duong_bao_gia(self, client: AsyncClient) -> None:
        """Tạo → chốt giá → thêm hạng mục → gửi. Gói Free không bị chặn ở cổng nào."""
        headers, _ = await _register_free(client)
        deal_id = await _make_deal(client, headers)

        tao = await client.post(f"/api/v1/proposals/from-template/{deal_id}", headers=headers)
        pid = tao.json()["data"]["id"]

        gia = await client.patch(
            f"/api/v1/proposals/{pid}/price", json={"price": 12_000_000}, headers=headers
        )
        assert gia.status_code == 200, gia.text

        noi_dung = gia.json()["data"]["content"]
        noi_dung["pricing_items"] = [
            {"label": "Thiết kế", "amount": 8_000_000, "due_type": "on_signing"},
            {"label": "Bàn giao", "amount": 4_000_000, "due_type": "on_completion"},
        ]
        luu = await client.patch(
            f"/api/v1/proposals/{pid}",
            json={"deal_id": deal_id, "content": noi_dung},
            headers=headers,
        )
        assert luu.status_code == 200, luu.text

        gui = await client.patch(
            f"/api/v1/proposals/{pid}/status", json={"status": "sent"}, headers=headers
        )
        assert gui.status_code == 200, gui.text


class TestKhongTuNhayTrangThai:
    async def test_khong_tao_thang_bao_gia_da_chap_nhan(
        self, client: AsyncClient, db_session
    ) -> None:
        """`status` từng là `str` tự do và ghi THẲNG vào DB.

        `POST /proposals {"status": "accepted"}` tạo ngay một báo giá đã-chấp-nhận, bỏ qua toàn
        bộ `transition_status`: cổng chưa-chốt-giá, cổng hạng mục 0đ, cổng tổng-lệch-giá-chào và
        cả bảng chuyển trạng thái hợp lệ — rồi từ đó tạo hợp đồng được luôn.
        """
        headers, _ = await _auth_with_profession(client, db_session, "ui-ux-design")
        deal_id = await _make_deal(client, headers)

        resp = await client.post(
            "/api/v1/proposals",
            json={"deal_id": deal_id, "content": {}, "status": "accepted"},
            headers=headers,
        )
        assert resp.status_code == 422, resp.text

    async def test_van_tao_binh_thuong_khi_khong_gui_status(
        self, client: AsyncClient, db_session
    ) -> None:
        headers, _ = await _auth_with_profession(client, db_session, "ui-ux-design")
        deal_id = await _make_deal(client, headers)

        resp = await client.post(
            "/api/v1/proposals", json={"deal_id": deal_id, "content": {}}, headers=headers
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["data"]["status"] == "draft"


class TestOTrongBamSuaDuoc:
    """Không có phần này thì hai phần trên vô nghĩa: tờ giấy rỗng không bấm vào đâu được."""

    async def test_editable_render_ca_muc_dang_trong(
        self, client: AsyncClient, db_session
    ) -> None:
        headers, _ = await _auth_with_profession(client, db_session, "ui-ux-design")
        deal_id = await _make_deal(client, headers)
        tao = await client.post(f"/api/v1/proposals/from-template/{deal_id}", headers=headers)
        pid = tao.json()["data"]["id"]

        resp = await client.get(
            f"/api/v1/proposals/{pid}/preview?editable=true", headers=headers
        )
        assert resp.status_code == 200, resp.text
        html = resp.json()["data"]["html"]

        # Năm mục này bọc trong `{% if %}` nên trước đây rỗng là biến mất — mà biến mất thì
        # freelancer không có chỗ nào để bấm vào nhập.
        for field in (
            "payment_terms",
            "out_of_scope",
            "revision_policy",
            "standard_terms",
            "valid_until",
        ):
            assert f'data-field="{field}"' in html, field

    async def test_ban_khach_nhan_khong_co_o_rong(
        self, client: AsyncClient, db_session
    ) -> None:
        headers, _ = await _auth_with_profession(client, db_session, "ui-ux-design")
        deal_id = await _make_deal(client, headers)
        tao = await client.post(f"/api/v1/proposals/from-template/{deal_id}", headers=headers)
        pid = tao.json()["data"]["id"]

        resp = await client.get(f"/api/v1/proposals/{pid}/preview", headers=headers)
        html = resp.json()["data"]["html"]

        for field in ("payment_terms", "out_of_scope", "revision_policy", "standard_terms"):
            assert f'data-field="{field}"' not in html, field

    async def test_so_muc_van_lien_mach_o_che_do_sua(
        self, client: AsyncClient, db_session
    ) -> None:
        # Mở thêm mục ở chế độ sửa mà quên bộ đếm động là tờ giấy nhảy số, khách đọc tưởng bị
        # cắt bớt. Bộ đếm đã có sẵn, bài này giữ nó không bị phá.
        headers, _ = await _auth_with_profession(client, db_session, "ui-ux-design")
        deal_id = await _make_deal(client, headers)
        tao = await client.post(f"/api/v1/proposals/from-template/{deal_id}", headers=headers)
        pid = tao.json()["data"]["id"]

        resp = await client.get(
            f"/api/v1/proposals/{pid}/preview?editable=true", headers=headers
        )
        html = resp.json()["data"]["html"]

        so_muc = [int(n) for n in re.findall(r"<h2>(\d+)\.", html)]
        assert so_muc == list(range(1, len(so_muc) + 1)), so_muc
        # Chế độ sửa mở thêm hai mục (Điều khoản bổ sung, Điều khoản chuẩn) so với bản khách
        # nhận — nếu không thì bài này xanh một cách vô nghĩa.
        assert len(so_muc) == 11, so_muc
