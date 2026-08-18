"""Mẫu NHIỀU KHỐI, chạy hết đường từ API.

Bổ sung cho `test_term_templates.py` (mẫu một-khối kiểu cũ). Ba thứ khoá ở đây:
mẫu điền nhiều mục thật, bộ chọn xem trước được, và freelancer chưa đặt nghề không mất mẫu.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import insert

from src.infrastructure.database.models import SystemTemplateModel
from src.main import app
from src.shared.dependencies.ai import get_ai_facade
from tests.integration.modules.proposals.test_generate_from_deal import (
    _make_deal,
    _PermissiveAIFacade,
)
from tests.integration.modules.proposals.test_term_templates import _auth_with_profession


async def _seed(
    db_session,
    *,
    admin_id: str,
    content: dict,
    template_type: str = "proposal",
    profession: str | None = None,
    name: str = "Mẫu nhiều khối",
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


@pytest.fixture(autouse=True)
def _permissive_ai():
    app.dependency_overrides[get_ai_facade] = lambda: _PermissiveAIFacade()
    yield
    app.dependency_overrides.pop(get_ai_facade, None)


class TestMauNhieuKhoi:
    async def test_mau_dien_nhieu_muc_cua_to_bao_gia(
        self, client: AsyncClient, db_session
    ) -> None:
        headers, uid = await _auth_with_profession(client, db_session, "ui-ux-design")
        tid = await _seed(
            db_session,
            admin_id=uid,
            content={
                "out_of_scope": ["Mua font bản quyền", "Chi phí in ấn"],
                "revision_policy": "2 vòng chỉnh sửa miễn phí.",
                "standard_terms": "Bàn giao file nguồn sau khi thanh toán đủ.",
            },
        )
        deal_id = await _make_deal(client, headers)

        resp = await client.post(
            f"/api/v1/proposals/generate-from-deal/{deal_id}?template_id={tid}", headers=headers
        )
        assert resp.status_code == 201, resp.text
        content = resp.json()["data"]["content"]

        assert content["out_of_scope"] == ["Mua font bản quyền", "Chi phí in ấn"]
        assert content["revision_policy"] == "2 vòng chỉnh sửa miễn phí."
        assert content["standard_terms"] == "Bàn giao file nguồn sau khi thanh toán đủ."

    async def test_mau_khong_lam_doi_mot_dong_tien_nao(
        self, client: AsyncClient, db_session
    ) -> None:
        """Bất biến quan trọng nhất, kiểm qua đường API thật.

        Cổng gửi báo giá, `resolve_cost_items` và bộ sinh task thu tiền cùng dựa trên "tổng
        hạng mục = giá chào khách". Một mẫu DÙNG CHUNG mà ghi đè được tiền là phá bất biến ấy
        từ bên ngoài, im lặng.
        """
        headers, uid = await _auth_with_profession(client, db_session, "ui-ux-design")
        deal_id = await _make_deal(client, headers)

        khong_mau = await client.post(
            f"/api/v1/proposals/generate-from-deal/{deal_id}", headers=headers
        )
        goc = khong_mau.json()["data"]["content"].get("pricing_detail")

        tid = await _seed(
            db_session,
            admin_id=uid,
            content={
                "standard_terms": "Điều khoản thật",
                "pricing_items": [{"label": "Mẫu chèn bậy", "amount": 1}],
                "pricing_detail": {"final_price": 1},
            },
        )
        deal2 = await _make_deal(client, headers)
        co_mau = await client.post(
            f"/api/v1/proposals/generate-from-deal/{deal2}?template_id={tid}", headers=headers
        )
        content = co_mau.json()["data"]["content"]

        assert content["standard_terms"] == "Điều khoản thật"
        assert content.get("pricing_detail") == goc
        assert content.get("pricing_items") in (None, [])

    async def test_valid_days_chi_ap_khi_freelancer_chua_tu_dat_han(
        self, client: AsyncClient, db_session
    ) -> None:
        headers, uid = await _auth_with_profession(client, db_session, "ui-ux-design")
        tid = await _seed(
            db_session, admin_id=uid, content={"standard_terms": "x", "valid_days": 30}
        )
        deal_id = await _make_deal(client, headers)

        resp = await client.post(
            f"/api/v1/proposals/generate-from-deal/{deal_id}?template_id={tid}", headers=headers
        )
        assert resp.status_code == 201, resp.text
        # Mẫu đặt hạn hộ vì freelancer chưa đặt gì.
        assert resp.json()["data"]["content"].get("valid_until")

    async def test_mau_hop_dong_dien_dung_cac_dieu_cua_no(
        self, client: AsyncClient, db_session
    ) -> None:
        headers, uid = await _auth_with_profession(client, db_session, "ui-ux-design")
        tid = await _seed(
            db_session,
            admin_id=uid,
            template_type="contract",
            content={
                "ip_ownership": "Bàn giao toàn bộ quyền sau thanh toán đủ.",
                "termination_clause": "Báo trước 15 ngày bằng văn bản.",
            },
        )
        resp = await client.get("/api/v1/contracts/term-templates", headers=headers)
        assert resp.status_code == 200
        assert any(t["id"] == tid for t in resp.json()["data"])


class TestBoChonXemTruocDuoc:
    async def test_tra_ve_khoi_va_trich_doan_va_nghe(
        self, client: AsyncClient, db_session
    ) -> None:
        # Bản trước chỉ trả {id, name} nên hai mẫu khác nhau nhìn y hệt nhau trong bộ chọn.
        headers, uid = await _auth_with_profession(client, db_session, "ui-ux-design")
        await _seed(
            db_session,
            admin_id=uid,
            profession="ui-ux-design",
            name="Bàn giao file nguồn",
            content={
                "out_of_scope": ["Mua font bản quyền"],
                "standard_terms": "Bàn giao file nguồn sau khi thanh toán đủ.",
            },
        )

        resp = await client.get("/api/v1/proposals/term-templates", headers=headers)
        assert resp.status_code == 200, resp.text
        item = next(t for t in resp.json()["data"] if t["name"] == "Bàn giao file nguồn")

        assert item["profession"] == "ui-ux-design"
        assert item["blocks"] == ["Ngoài phạm vi", "Điều khoản chuẩn"]
        assert "Mua font bản quyền" in item["preview"]

    async def test_mau_cu_chi_co_body_van_co_nhan(
        self, client: AsyncClient, db_session
    ) -> None:
        headers, uid = await _auth_with_profession(client, db_session, "ui-ux-design")
        await _seed(
            db_session, admin_id=uid, name="Mẫu kiểu cũ", content={"body": "Điều khoản cũ"}
        )

        resp = await client.get("/api/v1/proposals/term-templates", headers=headers)
        item = next(t for t in resp.json()["data"] if t["name"] == "Mẫu kiểu cũ")
        assert item["blocks"] == ["Điều khoản chuẩn"]
        assert item["preview"] == "Điều khoản cũ"


class TestChuaDatNgheThiKhongMatMau:
    async def test_freelancer_chua_dat_nghe_van_thay_mau_gan_nghe(
        self, client: AsyncClient, db_session
    ) -> None:
        """Lỗ im lặng của bản trước.

        Truy vấn chỉ lấy `profession IS NULL` khi freelancer chưa khai nghề → mọi mẫu gắn nghề
        biến mất, đúng lúc người dùng mới nhất (chưa kịp điền hồ sơ) cần mẫu nhất. Họ kết luận
        admin chưa soạn mẫu nào.
        """
        headers, uid = await _auth_with_profession(client, db_session, None)
        await _seed(
            db_session,
            admin_id=uid,
            profession="ui-ux-design",
            name="Mẫu gắn nghề",
            content={"standard_terms": "x"},
        )
        await _seed(
            db_session, admin_id=uid, name="Mẫu dùng chung", content={"standard_terms": "y"}
        )

        resp = await client.get("/api/v1/proposals/term-templates", headers=headers)
        names = {t["name"] for t in resp.json()["data"]}
        assert {"Mẫu gắn nghề", "Mẫu dùng chung"} <= names

    async def test_chua_dat_nghe_van_chon_duoc_mau_gan_nghe(
        self, client: AsyncClient, db_session
    ) -> None:
        # Thấy mà không chọn được thì tệ hơn không thấy: bấm vào ăn 422.
        headers, uid = await _auth_with_profession(client, db_session, None)
        tid = await _seed(
            db_session,
            admin_id=uid,
            profession="ui-ux-design",
            content={"standard_terms": "Điều khoản của nghề"},
        )
        deal_id = await _make_deal(client, headers)

        resp = await client.post(
            f"/api/v1/proposals/generate-from-deal/{deal_id}?template_id={tid}", headers=headers
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["data"]["content"]["standard_terms"] == "Điều khoản của nghề"

    async def test_mau_tat_van_an_du_chua_dat_nghe(
        self, client: AsyncClient, db_session
    ) -> None:
        headers, uid = await _auth_with_profession(client, db_session, None)
        await _seed(
            db_session,
            admin_id=uid,
            name="Mẫu đang tắt",
            content={"standard_terms": "x"},
            is_active=False,
        )

        resp = await client.get("/api/v1/proposals/term-templates", headers=headers)
        assert all(t["name"] != "Mẫu đang tắt" for t in resp.json()["data"])


class TestBoChonBietMauNaoCoKhung:
    async def test_tra_ve_skeleton_blocks_de_tab_khung_mo_ta_dung(
        self, client: AsyncClient, db_session
    ) -> None:
        """Tab "Tự soạn từ khung" mô tả mẫu theo mục ĐÃ SOẠN KHUNG, không phải khối điều khoản.

        Hai danh sách này khác nhau thật: một mẫu có thể đầy điều khoản mà chưa soạn khung nào.
        Không tách ra thì freelancer chọn xong mới phát hiện tờ giấy gần như trống.
        """
        headers, uid = await _auth_with_profession(client, db_session, "ui-ux-design")
        await _seed(
            db_session,
            admin_id=uid,
            name="Mẫu có cả hai",
            content={
                "standard_terms": "Điều khoản chuẩn",
                "project_overview": "Tổng quan mẫu",
                "timeline": "4 tuần",
            },
        )

        resp = await client.get("/api/v1/proposals/term-templates", headers=headers)
        item = next(t for t in resp.json()["data"] if t["name"] == "Mẫu có cả hai")

        assert item["blocks"] == ["Điều khoản chuẩn"]
        # CHỈ phần thân. Kể luôn "Điều khoản chuẩn" vào đây là đếm hai lần một thứ, và làm mẫu
        # thuần-điều-khoản trông như đã soạn cả tờ.
        assert item["skeleton_blocks"] == ["Tổng quan dự án", "Thời gian thực hiện"]

    async def test_mau_chi_co_dieu_khoan_thi_skeleton_blocks_rong(
        self, client: AsyncClient, db_session
    ) -> None:
        """Đúng hình dạng hai mẫu đang nằm trong DB thật.

        `out_of_scope` thuộc CẢ HAI bộ khoá. Đếm gộp thì mẫu này ra "có khung" và bộ chọn khoe
        "Soạn sẵn: Ngoài phạm vi" — nhưng chọn nó so với khung trắng chỉ khác đúng một mục ở
        cuối tờ giấy, còn phần phải gõ tay thì y hệt.
        """
        headers, uid = await _auth_with_profession(client, db_session, "ui-ux-design")
        await _seed(
            db_session,
            admin_id=uid,
            name="Chỉ điều khoản",
            content={"out_of_scope": ["Mua font"]},
        )

        resp = await client.get("/api/v1/proposals/term-templates", headers=headers)
        item = next(t for t in resp.json()["data"] if t["name"] == "Chỉ điều khoản")

        assert item["skeleton_blocks"] == []
        assert item["blocks"] == ["Ngoài phạm vi"]
