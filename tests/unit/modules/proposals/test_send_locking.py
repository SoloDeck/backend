"""`ProposalsService.send` — khoá deal → báo giá (không đứng chờ) và sự kiện chỉ phát SAU khi thư đi.

Repo là bản giả nên bài test ghi lại được THỨ TỰ các việc: đó là thứ khoá và sự kiện phụ thuộc vào.
Còn việc khoá có chặn được người khác THẬT hay không thì phải có hai phiên DB thật — xem phần đo
đồng thời ghi trong báo cáo, và `tests/integration/.../test_send_email.py` cho phần còn lại.
"""

import uuid
from collections.abc import Callable, Iterator
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.modules.proposals.application.service import ProposalsService
from src.modules.proposals.infrastructure.repository import RowLockedError
from src.modules.proposals.schemas.request import UpdateProposalRequest
from src.shared.exceptions.domain import BusinessRuleError, EmailDeliveryError, NotFoundError
from tests.unit.modules.proposals.test_service import _make_proposal

SEND_EMAIL = "src.shared.email.smtp.send_email"
EVENT_BUS = "src.modules.proposals.application.service.event_bus"
PDF_RENDERER = "src.modules.proposals.application.service.ProposalPdfRenderer"


class Harness:
    """Service + repo giả, và một danh sách `calls` ghi lại việc nào xảy ra TRƯỚC việc nào."""

    send_email: AsyncMock
    bus: MagicMock

    def __init__(self, *, status: str = "draft") -> None:
        self.user_id = uuid.uuid4()
        self.deal = SimpleNamespace(id=uuid.uuid4(), client_id=uuid.uuid4(), estimated_value=None)
        self.proposal = _make_proposal(
            status=status, deal_id=self.deal.id, owner_user_id=self.user_id
        )
        self.calls: list[str] = []

        repo = AsyncMock()
        repo.get_by_id.return_value = self.proposal
        repo.get_deal_for_update.side_effect = self._lock("khoa_deal", self.deal)
        repo.get_by_id_for_update.side_effect = self._lock("khoa_bao_gia", self.proposal)
        repo.get_sent_by_deal.return_value = None
        repo.get_client.return_value = SimpleNamespace(
            name="Công ty Nắng", email="khach@example.com"
        )
        repo.get_user.return_value = SimpleNamespace(
            full_name="Huỳnh Hòa", email="hoa@example.com"
        )
        repo.save.side_effect = lambda obj: obj
        self.repo = repo
        self.service = ProposalsService(db=AsyncMock(), repo=repo)

    def _lock(self, label: str, row: object) -> Callable[..., object]:
        async def lock(_id: object, _owner: object, *, nowait: bool = False) -> object:
            self.calls.append(f"{label}(nowait={nowait})")
            return row

        return lock

    def record(self, label: str) -> Callable[..., None]:
        def note(*_args: object, **_kwargs: object) -> None:
            self.calls.append(label)

        return note


@pytest.fixture
def h() -> Iterator[Harness]:
    """Harness có sẵn các bản giả: dựng tờ báo giá, PDF, `send_email`, và bus sự kiện."""
    harness = Harness()
    document = SimpleNamespace(
        project_type="Web cà phê", pricing_total="5.000.000 ₫", valid_until="05/10/2026"
    )
    with (
        patch.object(ProposalsService, "_build_document", AsyncMock(return_value=document)),
        patch(PDF_RENDERER) as renderer,
        patch(SEND_EMAIL, new=AsyncMock(side_effect=harness.record("gui_thu"))) as send_email,
        patch(EVENT_BUS) as bus,
    ):
        renderer.return_value.render_pdf.return_value = b"%PDF-1.4 gia"
        bus.publish = AsyncMock(side_effect=harness.record("su_kien"))
        harness.send_email = send_email
        harness.bus = bus
        yield harness


class TestSendKhoaDealTruocBaoGiaSau:
    async def test_khoa_deal_roi_moi_khoa_bao_gia_va_ca_hai_deu_nowait(self, h: Harness) -> None:
        """Hai bản nháp KHÁC NHAU của một deal chỉ nối tiếp được nhau qua hàng deal; và mọi chỗ
        khoá cả hai hàng phải đi cùng một thứ tự, nếu không là có vòng chờ khoá."""
        await h.service.send(h.user_id, h.proposal.id)

        assert h.calls[:2] == ["khoa_deal(nowait=True)", "khoa_bao_gia(nowait=True)"]

    async def test_khoa_xong_het_roi_moi_gui_thu_va_phat_su_kien(self, h: Harness) -> None:
        await h.service.send(h.user_id, h.proposal.id)

        assert h.calls == [
            "khoa_deal(nowait=True)",
            "khoa_bao_gia(nowait=True)",
            "gui_thu",
            "su_kien",
        ]

    async def test_deal_dang_bi_giu_thi_409_ngay_va_khong_dong_toi_gi_nua(
        self, h: Harness
    ) -> None:
        h.repo.get_deal_for_update.side_effect = RowLockedError()

        with pytest.raises(BusinessRuleError, match="đang được gửi hoặc đang lưu"):
            await h.service.send(h.user_id, h.proposal.id)

        h.repo.get_by_id_for_update.assert_not_awaited()
        h.send_email.assert_not_awaited()
        h.repo.save.assert_not_awaited()
        h.bus.publish.assert_not_awaited()

    async def test_bao_gia_dang_bi_giu_thi_409_ngay_va_khong_gui_thu(self, h: Harness) -> None:
        h.repo.get_by_id_for_update.side_effect = RowLockedError()

        with pytest.raises(BusinessRuleError, match="Đợi vài giây rồi thử lại"):
            await h.service.send(h.user_id, h.proposal.id)

        h.send_email.assert_not_awaited()
        h.repo.save.assert_not_awaited()
        assert h.proposal.status == "draft"

    async def test_bao_gia_khong_co_that_thi_404_va_khong_khoa_gi(self, h: Harness) -> None:
        h.repo.get_by_id.return_value = None

        with pytest.raises(NotFoundError):
            await h.service.send(h.user_id, h.proposal.id)

        h.repo.get_deal_for_update.assert_not_awaited()
        h.repo.get_by_id_for_update.assert_not_awaited()

    async def test_bao_gia_bi_xoa_giua_luc_doc_va_khoa_thi_404(self, h: Harness) -> None:
        # Đọc không khoá thấy, tới lúc khoá thì hàng đã biến mất.
        h.repo.get_by_id_for_update.side_effect = h._lock("khoa_bao_gia", None)

        with pytest.raises(NotFoundError):
            await h.service.send(h.user_id, h.proposal.id)

        h.send_email.assert_not_awaited()

    async def test_da_gui_roi_thi_noi_chi_ban_nhap_moi_gui_duoc_va_khong_co_thu(
        self, h: Harness
    ) -> None:
        """Gửi TUẦN TỰ lần hai (lượt trước đã commit) ra đúng câu cũ, không phải câu "đang bận"."""
        h.proposal.status = "sent"

        with pytest.raises(BusinessRuleError, match="Chỉ bản nháp mới gửi được"):
            await h.service.send(h.user_id, h.proposal.id)

        h.send_email.assert_not_awaited()
        h.bus.publish.assert_not_awaited()

    async def test_trang_thai_duoc_doc_lai_sau_khi_giu_khoa_chu_khong_dung_ban_doc_truoc(
        self, h: Harness
    ) -> None:
        """Bản đọc KHÔNG khoá nói `draft`, nhưng lúc giành được khoá thì lượt trước đã gửi xong."""
        stale = _make_proposal(status="draft", deal_id=h.deal.id, owner_user_id=h.user_id)
        fresh = _make_proposal(status="sent", deal_id=h.deal.id, owner_user_id=h.user_id)
        h.repo.get_by_id.return_value = stale
        h.repo.get_by_id_for_update.side_effect = h._lock("khoa_bao_gia", fresh)

        with pytest.raises(BusinessRuleError, match="Chỉ bản nháp mới gửi được"):
            await h.service.send(h.user_id, stale.id)

        h.send_email.assert_not_awaited()


class TestSetPriceVaUpdateCungThuTuKhoa:
    async def test_chot_gia_khoa_deal_truoc_bao_gia_va_khong_nowait(self, h: Harness) -> None:
        """`set_price` ghi cả `deal.estimated_value` nên cũng phải khoá deal TRƯỚC — đi ngược thứ tự
        của `send` là mỗi bên giữ một hàng chờ hàng kia."""
        await h.service.set_price(h.user_id, h.proposal.id, Decimal(7_000_000))

        assert h.calls == ["khoa_deal(nowait=False)", "khoa_bao_gia(nowait=False)"]
        assert h.deal.estimated_value == Decimal(7_000_000)

    async def test_khong_con_la_nhap_thi_tu_choi_va_khong_ghi_gia_vao_deal(self, h: Harness) -> None:
        h.proposal.status = "sent"

        with pytest.raises(BusinessRuleError, match="trạng thái nháp"):
            await h.service.set_price(h.user_id, h.proposal.id, Decimal(7_000_000))

        assert h.deal.estimated_value is None

    async def test_chot_gia_bao_gia_khong_co_that_thi_404(self, h: Harness) -> None:
        h.repo.get_by_id.return_value = None

        with pytest.raises(NotFoundError):
            await h.service.set_price(h.user_id, h.proposal.id, Decimal(1))

    async def test_sua_noi_dung_khong_dung_nowait_va_khong_khoa_deal(self, h: Harness) -> None:
        """Hai lượt tự lưu liên tiếp phải XẾP HÀNG, không được thất bại — nên `update` chờ khoá."""
        await h.service.update(h.user_id, h.proposal.id, UpdateProposalRequest(content={"a": 1}))

        h.repo.get_by_id_for_update.assert_awaited_once_with(h.proposal.id, h.user_id)
        h.repo.get_deal_for_update.assert_not_awaited()


class TestSuKienChiPhatSauKhiThuDi:
    async def test_thu_di_thi_phat_dung_mot_su_kien_voi_noi_dung_cu(self, h: Harness) -> None:
        await h.service.send(h.user_id, h.proposal.id)

        h.bus.publish.assert_awaited_once_with(
            "proposals.proposal_sent",
            {
                "proposal_id": str(h.proposal.id),
                "deal_id": str(h.deal.id),
                "owner_user_id": str(h.user_id),
            },
        )

    async def test_su_kien_phat_SAU_send_email_khong_phai_truoc(self, h: Harness) -> None:
        """Nơi nhận sự kiện (thông báo, Zalo...) chạy NGOÀI phạm vi rollback. Phát trước khi thư
        đi được thì thư hỏng, báo giá hoàn về `draft`, còn người ta đã bị báo "đã gửi" mất rồi."""
        await h.service.send(h.user_id, h.proposal.id)

        assert h.calls.index("gui_thu") < h.calls.index("su_kien")

    async def test_thu_hong_thi_khong_co_su_kien_nao(self, h: Harness) -> None:
        h.send_email.side_effect = EmailDeliveryError("Hộp thư hệ thống đang hỏng.", "auth")

        with pytest.raises(EmailDeliveryError):
            await h.service.send(h.user_id, h.proposal.id)

        h.bus.publish.assert_not_awaited()

    async def test_transition_status_publish_event_false_chot_trang_thai_nhung_im_lang(
        self, h: Harness
    ) -> None:
        proposal = await h.service.transition_status(
            h.user_id, h.proposal.id, "sent", publish_event=False
        )

        assert proposal.status == "sent"
        h.bus.publish.assert_not_awaited()

    async def test_publish_event_false_cung_ap_cho_accepted(self, h: Harness) -> None:
        h.proposal.status = "sent"

        proposal = await h.service.transition_status(
            h.user_id, h.proposal.id, "accepted", publish_event=False
        )

        assert proposal.status == "accepted"
        h.bus.publish.assert_not_awaited()

    async def test_mac_dinh_van_phat_ngay_nhu_cu_cho_duong_ghi_nhan_tay(self, h: Harness) -> None:
        """`PATCH .../status` gọi không kèm cờ nên hành vi cũ giữ nguyên."""
        await h.service.transition_status(h.user_id, h.proposal.id, "sent")

        h.bus.publish.assert_awaited_once()
        assert h.bus.publish.await_args.args[0] == "proposals.proposal_sent"
