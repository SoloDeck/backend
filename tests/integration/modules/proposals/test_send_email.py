"""POST /proposals/{id}/send gửi EMAIL thật kèm PDF — và gửi hỏng thì không đánh dấu đã gửi.

Trước đây endpoint này chỉ đổi trạng thái thành `sent` mà không gửi gì: khách không nhận được
báo giá nào trong khi hệ thống và màn hình đều ghi "đã gửi".
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import ProposalModel
from src.infrastructure.database.session import get_db_session
from src.main import app
from src.modules.proposals.application.service import DEFAULT_VALID_DAYS
from src.modules.proposals.infrastructure.repository import ProposalsRepository, RowLockedError
from src.shared.events.bus import event_bus
from src.shared.exceptions.domain import EmailDeliveryError
from tests.integration.modules.proposals.conftest import FAKE_PDF
from tests.integration.modules.proposals.test_proposals_public_api import (
    _auth,
    _create_client,
    _create_deal,
)

# Cổng gửi đòi hạng mục chi phí (mục 7) và tổng các dòng phải KHỚP giá chào.
SENDABLE_CONTENT = {
    "body": "proposal body",
    "pricing": {"total": 5_000_000, "currency": "VND"},
    "pricing_items": [
        {"label": "Thiết kế", "amount": 2_000_000},
        {"label": "Phát triển", "amount": 3_000_000},
    ],
}


async def _create_draft_proposal(http: AsyncClient, headers: dict, deal_id: str) -> str:
    resp = await http.post(
        "/api/v1/proposals",
        json={"deal_id": deal_id, "content": SENDABLE_CONTENT},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _get_status(http: AsyncClient, headers: dict, proposal_id: str) -> str:
    resp = await http.get(f"/api/v1/proposals/{proposal_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["status"]


def _dung_phien_nhu_that(db_session: AsyncSession) -> None:
    """Dựng lại hành vi của `get_db_session` thật: thành công thì commit, ném lỗi thì rollback.

    Fixture `client` dùng bản đơn giản KHÔNG commit/rollback theo từng request. Bài nào cần xem
    "lỗi thì hoàn tác" phải gọi hàm này TRƯỚC khi tạo dữ liệu.
    """

    async def override_db_nhu_that() -> AsyncGenerator[AsyncSession]:
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db_session] = override_db_nhu_that


class TestGuiEmailKhachKemPdf:
    async def test_thu_di_toi_email_khach_kem_file_pdf(
        self, client: AsyncClient, gui_email_gia: AsyncMock
    ) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers, await _create_client(client, headers))
        proposal_id = await _create_draft_proposal(client, headers, deal_id)

        resp = await client.post(f"/api/v1/proposals/{proposal_id}/send", headers=headers)

        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "sent"
        gui_email_gia.assert_awaited_once()
        sent = gui_email_gia.await_args.kwargs
        assert sent["to"] == "khach@example.com"
        assert sent["subject"].startswith("Báo giá")
        assert "Acme" in sent["plain"]
        # Khách trả lời là về thẳng hộp thư của freelancer, tên hiển thị là tên freelancer.
        assert sent["from_name"] == "Test User"
        assert sent["reply_to"].endswith("@example.com")
        assert len(sent["attachments"]) == 1
        filename, data, mime = sent["attachments"][0]
        assert filename.startswith("bao-gia") and filename.endswith(".pdf")
        assert data == FAKE_PDF
        assert mime == "application/pdf"

    async def test_khach_chua_co_email_thi_chan_va_giu_nguyen_ban_nhap(
        self, client: AsyncClient, gui_email_gia: AsyncMock
    ) -> None:
        headers = await _auth(client)
        resp = await client.post(
            "/api/v1/clients",
            json={"name": "Khach khong email", "status": "prospect"},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        deal_id = await _create_deal(client, headers, resp.json()["data"]["id"])
        proposal_id = await _create_draft_proposal(client, headers, deal_id)

        sent = await client.post(f"/api/v1/proposals/{proposal_id}/send", headers=headers)

        assert sent.status_code == 409, sent.text
        assert "chưa có email" in sent.json()["error"]["message"]
        gui_email_gia.assert_not_awaited()
        assert await _get_status(client, headers, proposal_id) == "draft"

    async def test_gui_hong_thi_khong_danh_dau_da_gui(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        gui_email_gia: AsyncMock,
    ) -> None:
        """Bản nháp phải nằm nguyên khi SMTP hỏng, để freelancer thấy lỗi và gửi lại được.

        Việc hoàn tác đến từ `get_db_session` thật (rollback khi route ném lỗi). Fixture `client`
        dùng bản đơn giản KHÔNG commit/rollback theo từng request, nên bài này dựng lại đúng hành vi
        của bản thật: thành công thì commit, ném lỗi thì rollback riêng request đó.
        """

        async def override_db_nhu_that() -> AsyncGenerator[AsyncSession]:
            try:
                yield db_session
                await db_session.commit()
            except Exception:
                await db_session.rollback()
                raise

        app.dependency_overrides[get_db_session] = override_db_nhu_that
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers, await _create_client(client, headers))
        proposal_id = await _create_draft_proposal(client, headers, deal_id)
        gui_email_gia.side_effect = EmailDeliveryError("Hộp thư hệ thống đang hỏng.", reason="auth")

        resp = await client.post(f"/api/v1/proposals/{proposal_id}/send", headers=headers)

        assert resp.status_code == 502, resp.text
        assert resp.json()["error"]["code"] == "EMAIL_DELIVERY_FAILED"
        assert resp.json()["error"]["message"] == "Hộp thư hệ thống đang hỏng."
        assert await _get_status(client, headers, proposal_id) == "draft"

    async def test_ghi_nhan_tay_van_khong_gui_thu(
        self, client: AsyncClient, gui_email_gia: AsyncMock
    ) -> None:
        """Freelancer đã tự gửi qua Zalo rồi chỉ muốn ghi nhận: PATCH /status không gửi thư."""
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers, await _create_client(client, headers))
        proposal_id = await _create_draft_proposal(client, headers, deal_id)

        resp = await client.patch(
            f"/api/v1/proposals/{proposal_id}/status", json={"status": "sent"}, headers=headers
        )

        assert resp.status_code == 200, resp.text
        gui_email_gia.assert_not_awaited()
        assert await _get_status(client, headers, proposal_id) == "sent"


class TestCongNghiepVuDungTruocKhiGui:
    """Cổng chặn (chưa chốt giá, gửi lại bản đã gửi) thì KHÔNG được có thư nào bay ra.

    Gửi thư TRƯỚC khi chạy cổng nghĩa là khách nhận báo giá mà chính hệ thống sẽ từ chối, rồi
    freelancer mới thấy lỗi — thư đã đi thì không thu hồi được.
    """

    async def test_chua_chot_gia_thi_khong_co_thu_nao(
        self, client: AsyncClient, gui_email_gia: AsyncMock
    ) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers, await _create_client(client, headers))
        resp = await client.post(
            "/api/v1/proposals",
            json={"deal_id": deal_id, "content": {"body": "x"}},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text

        sent = await client.post(
            f"/api/v1/proposals/{resp.json()['data']['id']}/send", headers=headers
        )

        assert sent.status_code == 409, sent.text
        assert "Chưa chốt giá" in sent.json()["error"]["message"]
        gui_email_gia.assert_not_awaited()

    async def test_gui_lai_ban_da_gui_khong_phat_sinh_thu_thu_hai(
        self, client: AsyncClient, gui_email_gia: AsyncMock
    ) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers, await _create_client(client, headers))
        proposal_id = await _create_draft_proposal(client, headers, deal_id)
        first = await client.post(f"/api/v1/proposals/{proposal_id}/send", headers=headers)
        assert first.status_code == 200, first.text

        again = await client.post(f"/api/v1/proposals/{proposal_id}/send", headers=headers)

        assert again.status_code == 409, again.text
        assert "Chỉ bản nháp mới gửi được" in again.json()["error"]["message"]
        assert gui_email_gia.await_count == 1


class TestNoiDungThu:
    async def test_thu_lay_dung_so_lieu_tu_to_bao_gia(
        self, client: AsyncClient, gui_email_gia: AsyncMock
    ) -> None:
        """Tên dự án, tổng tiền, hạn và tên file đều lấy từ tờ báo giá, không phải chuỗi cứng."""
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers, await _create_client(client, headers))
        proposal_id = await _create_draft_proposal(client, headers, deal_id)

        resp = await client.post(f"/api/v1/proposals/{proposal_id}/send", headers=headers)

        assert resp.status_code == 200, resp.text
        sent = gui_email_gia.await_args.kwargs
        assert "Test deal" in sent["subject"]
        assert "5.000.000" in sent["plain"]
        assert "hiệu lực đến" in sent["plain"]
        assert sent["attachments"][0][0] == "bao-gia-test-deal.pdf"

    async def test_han_bao_gia_tinh_tu_ngay_gui_khong_phai_ngay_tao(
        self, client: AsyncClient, db_session: AsyncSession, gui_email_gia: AsyncMock
    ) -> None:
        """Nháp để 10 ngày rồi mới gửi: hạn phải tính từ NGÀY GỬI.

        Bảo vệ thứ tự "chốt trạng thái rồi mới dựng PDF": hạn tính từ `sent_at or created_at`,
        nên dựng PDF/thư TRƯỚC khi `sent_at` được ghi sẽ in ra hạn đã trôi mất từ lúc gửi.
        """
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers, await _create_client(client, headers))
        proposal_id = await _create_draft_proposal(client, headers, deal_id)
        await db_session.execute(
            update(ProposalModel)
            .where(ProposalModel.id == uuid.UUID(proposal_id))
            .values(created_at=datetime.now(UTC) - timedelta(days=10))
        )
        db_session.expire_all()

        resp = await client.post(f"/api/v1/proposals/{proposal_id}/send", headers=headers)

        assert resp.status_code == 200, resp.text
        han = (datetime.now(UTC).date() + timedelta(days=DEFAULT_VALID_DAYS)).strftime("%d/%m/%Y")
        assert f"Báo giá có hiệu lực đến: {han}" in gui_email_gia.await_args.kwargs["plain"]


class TestEmailKhachSaiDang:
    async def test_email_khong_hop_le_thi_chan_truoc_khi_gui(
        self, client: AsyncClient, gui_email_gia: AsyncMock
    ) -> None:
        """Email chắc chắn không gửi được (thiếu dấu chấm trong tên miền...) → 409 rõ ràng.

        Để lọt xuống SMTP thì người dùng chỉ nhận câu "lỗi hệ thống thư" chung chung, dù thử
        lại bao nhiêu lần cũng vô ích. Chặn TRƯỚC khi chốt trạng thái và dựng PDF.
        """
        headers = await _auth(client)
        resp = await client.post(
            "/api/v1/clients",
            json={"name": "Khach go sai email", "status": "prospect", "email": "khach@congty"},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        deal_id = await _create_deal(client, headers, resp.json()["data"]["id"])
        proposal_id = await _create_draft_proposal(client, headers, deal_id)

        sent = await client.post(f"/api/v1/proposals/{proposal_id}/send", headers=headers)

        assert sent.status_code == 409, sent.text
        assert "khach@congty" in sent.json()["error"]["message"]
        assert "không hợp lệ" in sent.json()["error"]["message"]
        gui_email_gia.assert_not_awaited()
        assert await _get_status(client, headers, proposal_id) == "draft"


class TestSuKienChiPhatSauKhiThuDi:
    """`proposals.proposal_sent` có người nghe thì họ chạy NGOÀI phạm vi rollback (thông báo, Zalo).
    Phát trước khi thư đi được là báo "đã gửi" cho một báo giá rồi bị hoàn về `draft`."""

    async def test_thu_di_roi_moi_phat_dung_mot_su_kien(
        self, client: AsyncClient, gui_email_gia: AsyncMock
    ) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers, await _create_client(client, headers))
        proposal_id = await _create_draft_proposal(client, headers, deal_id)
        thu_tu: list[str] = []
        gui_email_gia.side_effect = lambda **_: thu_tu.append("gui_thu")

        with patch.object(event_bus, "publish", new_callable=AsyncMock) as publish:
            publish.side_effect = lambda *_, **__: thu_tu.append("su_kien")
            resp = await client.post(f"/api/v1/proposals/{proposal_id}/send", headers=headers)

        assert resp.status_code == 200, resp.text
        assert thu_tu == ["gui_thu", "su_kien"]
        publish.assert_awaited_once()
        ten, noi_dung = publish.await_args.args
        assert ten == "proposals.proposal_sent"
        assert noi_dung["proposal_id"] == proposal_id
        assert noi_dung["deal_id"] == deal_id
        uuid.UUID(noi_dung["owner_user_id"])

    async def test_thu_hong_thi_khong_phat_su_kien_va_ban_nhap_nam_nguyen(
        self, client: AsyncClient, db_session: AsyncSession, gui_email_gia: AsyncMock
    ) -> None:
        _dung_phien_nhu_that(db_session)
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers, await _create_client(client, headers))
        proposal_id = await _create_draft_proposal(client, headers, deal_id)
        gui_email_gia.side_effect = EmailDeliveryError("Hộp thư hệ thống đang hỏng.", reason="auth")

        with patch.object(event_bus, "publish", new_callable=AsyncMock) as publish:
            resp = await client.post(f"/api/v1/proposals/{proposal_id}/send", headers=headers)

        assert resp.status_code == 502, resp.text
        publish.assert_not_awaited()
        assert await _get_status(client, headers, proposal_id) == "draft"

    async def test_ghi_nhan_tay_van_phat_su_kien_ngay_nhu_cu(
        self, client: AsyncClient, gui_email_gia: AsyncMock
    ) -> None:
        """`PATCH .../status` không có thư nào để đợi nên giữ hành vi cũ: phát ngay."""
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers, await _create_client(client, headers))
        proposal_id = await _create_draft_proposal(client, headers, deal_id)

        with patch.object(event_bus, "publish", new_callable=AsyncMock) as publish:
            resp = await client.patch(
                f"/api/v1/proposals/{proposal_id}/status", json={"status": "sent"}, headers=headers
            )

        assert resp.status_code == 200, resp.text
        publish.assert_awaited_once()
        assert publish.await_args.args[0] == "proposals.proposal_sent"
        gui_email_gia.assert_not_awaited()


class TestGuiDungDoVaKhoa:
    """Hai lượt gửi đụng nhau thì lượt sau nhận 409 NGAY, không đứng chờ khoá.

    Đo đồng thời thật cần hai phiên DB thật nên không nằm trong bộ test chạy chung một phiên này;
    ở đây ép việc "không giành được khoá" bằng cách để repo ném đúng ngoại lệ mà Postgres sinh ra.
    """

    async def test_deal_dang_bi_giu_thi_409_khong_thu_khong_doi_trang_thai(
        self, client: AsyncClient, gui_email_gia: AsyncMock
    ) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers, await _create_client(client, headers))
        proposal_id = await _create_draft_proposal(client, headers, deal_id)

        with patch.object(
            ProposalsRepository, "get_deal_for_update", AsyncMock(side_effect=RowLockedError())
        ) as khoa_deal:
            resp = await client.post(f"/api/v1/proposals/{proposal_id}/send", headers=headers)

        assert resp.status_code == 409, resp.text
        assert resp.json()["error"]["code"] == "BUSINESS_RULE_VIOLATION"
        assert "đang được gửi hoặc đang lưu ở một thao tác khác" in resp.json()["error"]["message"]
        assert khoa_deal.await_args.kwargs["nowait"] is True
        gui_email_gia.assert_not_awaited()
        assert await _get_status(client, headers, proposal_id) == "draft"

    async def test_bao_gia_dang_bi_giu_thi_409_khong_thu_khong_doi_trang_thai(
        self, client: AsyncClient, gui_email_gia: AsyncMock
    ) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers, await _create_client(client, headers))
        proposal_id = await _create_draft_proposal(client, headers, deal_id)

        with patch.object(
            ProposalsRepository, "get_by_id_for_update", AsyncMock(side_effect=RowLockedError())
        ) as khoa_bao_gia:
            resp = await client.post(f"/api/v1/proposals/{proposal_id}/send", headers=headers)

        assert resp.status_code == 409, resp.text
        assert "Đợi vài giây rồi thử lại" in resp.json()["error"]["message"]
        assert khoa_bao_gia.await_args.kwargs["nowait"] is True
        gui_email_gia.assert_not_awaited()
        assert await _get_status(client, headers, proposal_id) == "draft"

    async def test_sau_khi_het_ban_thi_gui_lai_duoc(
        self, client: AsyncClient, gui_email_gia: AsyncMock
    ) -> None:
        """409 "đang bận" là tạm thời: lượt thử lại sau đó đi bình thường."""
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers, await _create_client(client, headers))
        proposal_id = await _create_draft_proposal(client, headers, deal_id)
        with patch.object(
            ProposalsRepository, "get_deal_for_update", AsyncMock(side_effect=RowLockedError())
        ):
            busy = await client.post(f"/api/v1/proposals/{proposal_id}/send", headers=headers)
        assert busy.status_code == 409

        retry = await client.post(f"/api/v1/proposals/{proposal_id}/send", headers=headers)

        assert retry.status_code == 200, retry.text
        assert gui_email_gia.await_count == 1

    async def test_hai_ban_nhap_cung_deal_gui_tuan_tu_thi_ban_sau_thay_ban_truoc(
        self, client: AsyncClient, gui_email_gia: AsyncMock
    ) -> None:
        """Tại mọi thời điểm một deal chỉ có MỘT bản `sent`; bản gửi sau thay bản trước."""
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers, await _create_client(client, headers))
        first = await _create_draft_proposal(client, headers, deal_id)
        second = await _create_draft_proposal(client, headers, deal_id)

        r1 = await client.post(f"/api/v1/proposals/{first}/send", headers=headers)
        r2 = await client.post(f"/api/v1/proposals/{second}/send", headers=headers)

        assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)
        assert await _get_status(client, headers, first) == "superseded"
        assert await _get_status(client, headers, second) == "sent"
        assert gui_email_gia.await_count == 2

    async def test_nguoi_khac_khong_gui_duoc_bao_gia_cua_ban_va_chi_thay_404(
        self, client: AsyncClient, gui_email_gia: AsyncMock
    ) -> None:
        """Đọc không khoá để lấy `deal_id` cũng phải lọc theo chủ sở hữu."""
        owner = await _auth(client)
        deal_id = await _create_deal(client, owner, await _create_client(client, owner))
        proposal_id = await _create_draft_proposal(client, owner, deal_id)
        stranger = await _auth(client)

        sent = await client.post(f"/api/v1/proposals/{proposal_id}/send", headers=stranger)
        priced = await client.patch(
            f"/api/v1/proposals/{proposal_id}/price", json={"price": 5_000_000}, headers=stranger
        )

        assert sent.status_code == 404, sent.text
        assert priced.status_code == 404, priced.text
        gui_email_gia.assert_not_awaited()
        assert await _get_status(client, owner, proposal_id) == "draft"


class TestChotGiaSauKhiDoiThuTuKhoa:
    async def test_chot_gia_van_ghi_ca_vao_bao_gia_lan_deal(self, client: AsyncClient) -> None:
        """`set_price` giờ khoá deal rồi mới khoá báo giá; kết quả ghi ra vẫn y như cũ."""
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers, await _create_client(client, headers))
        proposal_id = await _create_draft_proposal(client, headers, deal_id)

        resp = await client.patch(
            f"/api/v1/proposals/{proposal_id}/price", json={"price": 7_000_000}, headers=headers
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["content"]["pricing_detail"]["final_price"] == 7_000_000
        deal = await client.get(f"/api/v1/deals/{deal_id}", headers=headers)
        assert Decimal(str(deal.json()["data"]["estimated_value"])) == Decimal(7_000_000)

    async def test_chot_gia_ban_da_gui_thi_van_bi_tu_choi_va_khong_dung_vao_deal(
        self, client: AsyncClient
    ) -> None:
        headers = await _auth(client)
        deal_id = await _create_deal(client, headers, await _create_client(client, headers))
        proposal_id = await _create_draft_proposal(client, headers, deal_id)
        sent = await client.post(f"/api/v1/proposals/{proposal_id}/send", headers=headers)
        assert sent.status_code == 200, sent.text
        before = (await client.get(f"/api/v1/deals/{deal_id}", headers=headers)).json()["data"]

        resp = await client.patch(
            f"/api/v1/proposals/{proposal_id}/price", json={"price": 9_000_000}, headers=headers
        )

        assert resp.status_code == 409, resp.text
        after = (await client.get(f"/api/v1/deals/{deal_id}", headers=headers)).json()["data"]
        assert after["estimated_value"] == before["estimated_value"]
