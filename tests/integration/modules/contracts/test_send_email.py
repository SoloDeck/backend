"""POST /contracts/{id}/send gửi EMAIL thật kèm PDF — và gửi hỏng thì không đánh dấu đã gửi.

Trước đây endpoint này chỉ đổi trạng thái thành `pending_signatures` mà không gửi gì: khách
không nhận được tờ hợp đồng nào trong khi màn hình ghi "đã gửi cho khách ký".
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.main import app
from src.modules.contracts.infrastructure.repository import ContractsRepository, RowLockedError
from src.shared.exceptions.domain import EmailDeliveryError
from tests.integration.modules.contracts.conftest import FAKE_PDF
from tests.integration.modules.contracts.test_contracts_api import (
    _auth,
    _create_accepted_proposal,
    _create_client,
    _create_contract,
    _create_deal,
)


async def _get_status(http: AsyncClient, headers: dict, contract_id: str) -> str:
    resp = await http.get(f"/api/v1/contracts/{contract_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["status"]


def _dung_phien_nhu_that(db_session: AsyncSession) -> None:
    """Dựng lại hành vi của `get_db_session` thật: thành công thì commit, ném lỗi thì rollback.

    Fixture `client` dùng bản đơn giản KHÔNG commit/rollback theo từng request. Bài nào cần phiên
    còn dùng được SAU một lỗi cơ sở dữ liệu thật phải gọi hàm này TRƯỚC khi tạo dữ liệu.
    """

    async def override_db_nhu_that() -> AsyncGenerator[AsyncSession]:
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db_session] = override_db_nhu_that


async def _add_draft_contract_to_same_deal(http: AsyncClient, headers: dict, contract_id: str) -> str:
    """Thêm một hợp đồng nháp NỮA vào cùng deal của `contract_id` (cùng báo giá đã chấp nhận)."""
    existing = (await http.get(f"/api/v1/contracts/{contract_id}", headers=headers)).json()["data"]
    return await _create_contract(
        http,
        headers,
        existing["deal_id"],
        existing["proposal_id"],
        existing["client_id"],
    )


async def _setup_draft_contract(
    http: AsyncClient, *, client_payload: dict | None = None
) -> tuple[dict, str]:
    """Trả `(headers, contract_id)` của một hợp đồng nháp. `client_payload` để tạo khách riêng."""
    headers = await _auth(http)
    if client_payload is None:
        client_id = await _create_client(http, headers)
    else:
        resp = await http.post("/api/v1/clients", json=client_payload, headers=headers)
        assert resp.status_code == 201, resp.text
        client_id = resp.json()["data"]["id"]
    deal_id = await _create_deal(http, headers, client_id)
    proposal_id = await _create_accepted_proposal(http, headers, deal_id)
    return headers, await _create_contract(http, headers, deal_id, proposal_id, client_id)


class TestGuiEmailKhachKemPdf:
    async def test_thu_di_toi_email_khach_kem_file_pdf(
        self, client: AsyncClient, gui_email_gia: AsyncMock
    ) -> None:
        headers, contract_id = await _setup_draft_contract(client)

        resp = await client.post(f"/api/v1/contracts/{contract_id}/send", headers=headers)

        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "pending_signatures"
        gui_email_gia.assert_awaited_once()
        sent = gui_email_gia.await_args.kwargs
        assert sent["to"] == "khach@example.com"
        assert sent["subject"].startswith("Hợp đồng")
        assert "Acme" in sent["plain"]
        assert sent["from_name"] == "Test User"
        assert sent["reply_to"].endswith("@example.com")
        assert len(sent["attachments"]) == 1
        filename, data, mime = sent["attachments"][0]
        assert filename.startswith("hop-dong") and filename.endswith(".pdf")
        assert data == FAKE_PDF
        assert mime == "application/pdf"

    async def test_khach_chua_co_email_thi_chan_va_giu_nguyen_ban_nhap(
        self, client: AsyncClient, gui_email_gia: AsyncMock
    ) -> None:
        headers, contract_id = await _setup_draft_contract(
            client, client_payload={"name": "Khach khong email", "status": "prospect"}
        )

        resp = await client.post(f"/api/v1/contracts/{contract_id}/send", headers=headers)

        assert resp.status_code == 409, resp.text
        assert "chưa có email" in resp.json()["error"]["message"]
        gui_email_gia.assert_not_awaited()
        assert await _get_status(client, headers, contract_id) == "draft"

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
        headers, contract_id = await _setup_draft_contract(client)
        gui_email_gia.side_effect = EmailDeliveryError("Hộp thư hệ thống đang hỏng.", reason="auth")

        resp = await client.post(f"/api/v1/contracts/{contract_id}/send", headers=headers)

        assert resp.status_code == 502, resp.text
        assert resp.json()["error"]["code"] == "EMAIL_DELIVERY_FAILED"
        assert resp.json()["error"]["message"] == "Hộp thư hệ thống đang hỏng."
        assert await _get_status(client, headers, contract_id) == "draft"


class TestGuiLaiVaGhiNhanTay:
    async def test_gui_lai_hop_dong_da_gui_khong_phat_sinh_thu_thu_hai(
        self, client: AsyncClient, gui_email_gia: AsyncMock
    ) -> None:
        headers, contract_id = await _setup_draft_contract(client)
        first = await client.post(f"/api/v1/contracts/{contract_id}/send", headers=headers)
        assert first.status_code == 200, first.text

        again = await client.post(f"/api/v1/contracts/{contract_id}/send", headers=headers)

        assert again.status_code >= 400, again.text
        assert "Chỉ hợp đồng nháp mới gửi được" in again.json()["error"]["message"]
        assert gui_email_gia.await_count == 1

    async def test_ghi_nhan_tay_van_khong_gui_thu(
        self, client: AsyncClient, gui_email_gia: AsyncMock
    ) -> None:
        """Freelancer đã tự gửi qua Zalo rồi chỉ muốn ghi nhận: PATCH /status không gửi thư."""
        headers, contract_id = await _setup_draft_contract(client)

        resp = await client.patch(
            f"/api/v1/contracts/{contract_id}/status",
            json={"status": "pending_signatures"},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        gui_email_gia.assert_not_awaited()
        assert await _get_status(client, headers, contract_id) == "pending_signatures"


class TestNoiDungThu:
    async def test_thu_lay_dung_so_lieu_tu_to_hop_dong(
        self, client: AsyncClient, gui_email_gia: AsyncMock
    ) -> None:
        """Tên dự án, số hợp đồng và tên file đều lấy từ tờ hợp đồng, không phải chuỗi cứng."""
        headers, contract_id = await _setup_draft_contract(client)

        resp = await client.post(f"/api/v1/contracts/{contract_id}/send", headers=headers)

        assert resp.status_code == 200, resp.text
        sent = gui_email_gia.await_args.kwargs
        assert "Test deal" in sent["subject"]
        assert "(số HD-" in sent["plain"]
        assert sent["attachments"][0][0] == "hop-dong-test-deal.pdf"


class TestEmailKhachSaiDang:
    async def test_email_khong_hop_le_thi_chan_truoc_khi_gui(
        self, client: AsyncClient, gui_email_gia: AsyncMock
    ) -> None:
        headers, contract_id = await _setup_draft_contract(
            client,
            client_payload={
                "name": "Khach go sai email",
                "status": "prospect",
                "email": "khach@congty",
            },
        )

        resp = await client.post(f"/api/v1/contracts/{contract_id}/send", headers=headers)

        assert resp.status_code == 409, resp.text
        assert "khach@congty" in resp.json()["error"]["message"]
        assert "không hợp lệ" in resp.json()["error"]["message"]
        gui_email_gia.assert_not_awaited()
        assert await _get_status(client, headers, contract_id) == "draft"
