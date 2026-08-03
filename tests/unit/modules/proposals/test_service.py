"""Unit tests for ProposalsService.transition_status."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.modules.proposals.application.service import (
    DEFAULT_VALID_DAYS,
    ProposalsService,
)
from src.shared.exceptions.domain import (
    BusinessRuleError,
    InvalidStateTransitionError,
    NotFoundError,
)


def _make_proposal(**kwargs) -> MagicMock:
    m = MagicMock()
    m.id = kwargs.get("id", uuid.uuid4())
    m.deal_id = kwargs.get("deal_id", uuid.uuid4())
    m.owner_user_id = kwargs.get("owner_user_id", uuid.uuid4())
    m.status = kwargs.get("status", "draft")
    m.sent_at = kwargs.get("sent_at")
    m.responded_at = kwargs.get("responded_at")
    # Có giá cụ thể để qua được cổng "không gửi báo giá không có giá". MagicMock mặc định
    # cho `.content` trả về mock (không phải dict) nên cổng chặn.  #Huynh
    m.content = kwargs.get("content", {"pricing": {"total": 5_000_000, "currency": "VND"}})
    return m


class TestTransitionStatus:
    async def test_draft_to_sent_succeeds(self) -> None:
        proposal = _make_proposal(status="draft")
        db = AsyncMock()
        db.scalar.side_effect = [proposal, None]  # _get_proposal, then no existing sent

        with patch("src.modules.proposals.application.service.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock()
            svc = ProposalsService(db=db)
            result = await svc.transition_status(proposal.owner_user_id, proposal.id, "sent")

        assert result.status == "sent"
        assert result.sent_at is not None
        mock_bus.publish.assert_awaited_once()
        call_args = mock_bus.publish.call_args[0]
        assert call_args[0] == "proposals.proposal_sent"

    async def test_draft_to_sent_supersedes_existing_sent(self) -> None:
        deal_id = uuid.uuid4()
        proposal = _make_proposal(status="draft", deal_id=deal_id)
        existing_sent = _make_proposal(status="sent", deal_id=deal_id)
        db = AsyncMock()
        db.scalar.side_effect = [proposal, existing_sent]

        with patch("src.modules.proposals.application.service.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock()
            svc = ProposalsService(db=db)
            await svc.transition_status(proposal.owner_user_id, proposal.id, "sent")

        assert existing_sent.status == "superseded"

    async def test_sent_to_accepted_sets_responded_at(self) -> None:
        proposal = _make_proposal(status="sent")
        db = AsyncMock()
        db.scalar.return_value = proposal

        with patch("src.modules.proposals.application.service.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock()
            svc = ProposalsService(db=db)
            result = await svc.transition_status(proposal.owner_user_id, proposal.id, "accepted")

        assert result.status == "accepted"
        assert result.responded_at is not None
        call_args = mock_bus.publish.call_args[0]
        assert call_args[0] == "proposals.proposal_accepted"

    async def test_sent_to_rejected_sets_responded_at(self) -> None:
        proposal = _make_proposal(status="sent")
        db = AsyncMock()
        db.scalar.return_value = proposal

        with patch("src.modules.proposals.application.service.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock()
            svc = ProposalsService(db=db)
            result = await svc.transition_status(proposal.owner_user_id, proposal.id, "rejected")

        assert result.status == "rejected"
        assert result.responded_at is not None

    async def test_invalid_transition_raises(self) -> None:
        proposal = _make_proposal(status="draft")
        db = AsyncMock()
        db.scalar.return_value = proposal

        svc = ProposalsService(db=db)
        with pytest.raises(InvalidStateTransitionError):
            await svc.transition_status(proposal.owner_user_id, proposal.id, "accepted")

    async def test_terminal_status_raises(self) -> None:
        proposal = _make_proposal(status="accepted")
        db = AsyncMock()
        db.scalar.return_value = proposal

        svc = ProposalsService(db=db)
        with pytest.raises(InvalidStateTransitionError):
            await svc.transition_status(proposal.owner_user_id, proposal.id, "sent")

    async def test_not_found_raises(self) -> None:
        db = AsyncMock()
        db.scalar.return_value = None

        svc = ProposalsService(db=db)
        with pytest.raises(NotFoundError):
            await svc.transition_status(uuid.uuid4(), uuid.uuid4(), "sent")


class TestTongMocThanhToanPhaiBang100:
    """Không gửi được báo giá mà các đợt thanh toán không cộng thành 100%.

    Đo thật: một báo giá có ba đợt 50% + 50% + 30% = 130% vẫn in ra bảng "8. Điều Khoản
    Thanh Toán" và vẫn gửi được cho khách. Khách tự cộng ra 130% thì hoặc mình mất uy tín,
    hoặc cãi nhau lúc đòi tiền.  #Huynh
    """

    @staticmethod
    def _content(milestones: list[dict]) -> dict:
        return {
            "pricing": {"total": 5_000_000, "currency": "VND"},
            "payment_milestones": milestones,
        }

    async def test_tong_khac_100_thi_chan_gui(self) -> None:
        proposal = _make_proposal(
            status="draft",
            content=self._content(
                [
                    {"label": "Đặt cọc khi ký hợp đồng", "percent": 50},
                    {"label": "Thanh toán khi bàn giao", "percent": 50},
                    {"label": "avc", "percent": 30},
                ]
            ),
        )
        db = AsyncMock()
        db.scalar.side_effect = [proposal, None]

        svc = ProposalsService(db=db)
        with pytest.raises(BusinessRuleError, match="130%"):
            await svc.transition_status(proposal.owner_user_id, proposal.id, "sent")
        # Chặn là chặn HẲN: trạng thái không được nhúc nhích.
        assert proposal.status == "draft"

    async def test_tong_dung_100_thi_gui_duoc(self) -> None:
        proposal = _make_proposal(
            status="draft",
            content=self._content(
                [
                    {"label": "Đặt cọc khi ký hợp đồng", "percent": 50},
                    {"label": "Thanh toán khi bàn giao", "percent": 50},
                ]
            ),
        )
        db = AsyncMock()
        db.scalar.side_effect = [proposal, None]

        with patch("src.modules.proposals.application.service.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock()
            result = await ProposalsService(db=db).transition_status(
                proposal.owner_user_id, proposal.id, "sent"
            )
        assert result.status == "sent"

    async def test_lich_co_dot_ghi_so_tien_thi_khong_chan(self) -> None:
        # Lịch hỗn hợp: cộng % không có nghĩa gì, chặn là chặn oan.
        proposal = _make_proposal(
            status="draft",
            content=self._content(
                [
                    {"label": "Đặt cọc", "percent": 50},
                    {"label": "Phần còn lại", "amount": "2.500.000 ₫"},
                ]
            ),
        )
        db = AsyncMock()
        db.scalar.side_effect = [proposal, None]

        with patch("src.modules.proposals.application.service.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock()
            result = await ProposalsService(db=db).transition_status(
                proposal.owner_user_id, proposal.id, "sent"
            )
        assert result.status == "sent"

    async def test_bao_gia_khong_co_moc_thi_khong_chan(self) -> None:
        # Báo giá cũ không có mốc cấu trúc — chúng rơi về lịch chuẩn 50/50 lúc sinh task,
        # khoá chúng lại là khoá luôn dữ liệu cũ.
        proposal = _make_proposal(status="draft")
        db = AsyncMock()
        db.scalar.side_effect = [proposal, None]

        with patch("src.modules.proposals.application.service.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock()
            result = await ProposalsService(db=db).transition_status(
                proposal.owner_user_id, proposal.id, "sent"
            )
        assert result.status == "sent"


class TestNgayTrenBaoGia:
    """Ngày trên tờ báo giá phải ĐỨNG YÊN.

    Bản trước lấy `date.today()` cho cả "ngày lập" lẫn "hiệu lực đến", tính lại mỗi lần
    render. Báo giá lập 17/07 ghi "hiệu lực đến 21/07"; mở đúng nó ngày 30/07 thì thành
    "lập 30/07, hiệu lực đến 03/08" — hạn trườn tới mỗi ngày một ngày, tức là không bao giờ
    hết hạn, và tờ giấy khai lại cả ngày sinh của chính nó.

    MỌI ngày ở đây phải nằm trong QUÁ KHỨ, cách hôm nay đủ xa. Lần đầu tôi viết bộ test này
    với `created_at` = đúng ngày chạy test, nên `date.today()` trùng luôn `created_at` —
    logic hỏng vẫn xanh 9/10. Test chỉ đúng vào một ngày duy nhất trong năm thì không canh
    được gì cả.  #Huynh
    """

    # Cố định trong quá khứ: hôm nay là ngày nào thì hai mốc này cũng không đổi.
    TAO_LUC = datetime(2026, 3, 5, 9, 0, tzinfo=UTC)
    GUI_LUC = datetime(2026, 3, 20, 9, 0, tzinfo=UTC)

    @staticmethod
    def _svc_with(proposal) -> tuple[ProposalsService, MagicMock]:
        db = AsyncMock()
        db.scalar.return_value = proposal

        deal = MagicMock()
        deal.project_type = "Web bán cà phê"
        deal.title = "Web bán cà phê"
        deal.client_id = None

        user = MagicMock()
        user.full_name = "Huynh Hoa"
        user.email = "hoa@example.com"
        user.phone = "0901234567"

        svc = ProposalsService(db=db)
        svc.repo = MagicMock()
        svc.repo.get_by_id = AsyncMock(return_value=proposal)
        svc.repo.get_deal = AsyncMock(return_value=deal)
        svc.repo.get_client = AsyncMock(return_value=None)
        svc.repo.get_user = AsyncMock(return_value=user)
        return svc, deal

    async def test_ngay_lap_la_ngay_TAO_chu_khong_phai_hom_nay(self) -> None:
        proposal = _make_proposal()
        proposal.created_at = self.TAO_LUC
        proposal.sent_at = None
        proposal.content = {}
        svc, _ = self._svc_with(proposal)

        doc = await svc._build_document(proposal.owner_user_id, proposal.id)

        # Chạy test hôm nay hay sang năm thì dòng này vẫn phải là ngày TẠO.
        assert doc.proposal_date == "05/03/2026"

    async def test_han_hieu_luc_dung_yen_theo_ngay_tao(self) -> None:
        proposal = _make_proposal()
        proposal.created_at = self.TAO_LUC
        proposal.sent_at = None
        proposal.content = {}
        svc, _ = self._svc_with(proposal)

        doc = await svc._build_document(proposal.owner_user_id, proposal.id)

        han = (self.TAO_LUC + timedelta(days=DEFAULT_VALID_DAYS)).strftime("%d/%m/%Y")
        assert doc.valid_until == han

    async def test_dong_ho_chay_tu_luc_GUI_chu_khong_phai_luc_soan(self) -> None:
        # Soạn nháp để đó một tuần rồi mới gửi thì không có lý gì hạn đã trôi mất một tuần
        # trước khi khách kịp đọc.
        proposal = _make_proposal()
        proposal.created_at = self.TAO_LUC
        proposal.sent_at = self.GUI_LUC
        proposal.content = {}
        svc, _ = self._svc_with(proposal)

        doc = await svc._build_document(proposal.owner_user_id, proposal.id)

        assert doc.proposal_date == "20/03/2026"
        han = (self.GUI_LUC + timedelta(days=DEFAULT_VALID_DAYS)).strftime("%d/%m/%Y")
        assert doc.valid_until == han

    async def test_freelancer_tu_dat_han_thi_lay_dung_thu_ho_dat(self) -> None:
        proposal = _make_proposal()
        proposal.created_at = self.TAO_LUC
        proposal.sent_at = None
        proposal.content = {"valid_until": "2026-08-31"}
        svc, _ = self._svc_with(proposal)

        doc = await svc._build_document(proposal.owner_user_id, proposal.id)

        assert doc.valid_until == "31/08/2026"

    @pytest.mark.parametrize("rac", ["", "  ", "31/08/2026", "hom nao do", None, 12345])
    async def test_han_rac_thi_roi_ve_mac_dinh_chu_khong_no(self, rac) -> None:
        # `content` là JSONB tự do — không ai validate. Một khoá hỏng không được phép làm
        # sập cả việc xuất PDF.
        proposal = _make_proposal()
        proposal.created_at = self.TAO_LUC
        proposal.sent_at = None
        proposal.content = {"valid_until": rac}
        svc, _ = self._svc_with(proposal)

        doc = await svc._build_document(proposal.owner_user_id, proposal.id)

        han = (self.TAO_LUC + timedelta(days=DEFAULT_VALID_DAYS)).strftime("%d/%m/%Y")
        assert doc.valid_until == han


class TestCongChanTongHangMuc:
    """Không cho gửi khi tổng các hạng mục chi phí ≠ giá chào khách.

    Cùng lý do với cổng "tổng mốc thanh toán = 100%": khách cầm tờ báo giá tự cộng cột
    "Thành tiền" ra một số, rồi đọc dòng "Tổng báo giá" ra số khác. Mất uy tín ngay tại
    bàn, và không cãi được.  #Huynh
    """

    @staticmethod
    def _proposal_with(items, total=500_000_000):
        return _make_proposal(
            status="draft",
            content={
                "pricing_detail": {"final_price": total, "suggested": total},
                "pricing_items": items,
            },
        )

    async def test_chan_gui_khi_tong_lech_gia_chao(self) -> None:
        proposal = self._proposal_with(
            [
                {"label": "Backend", "amount": 200_000_000},
                {"label": "Frontend", "amount": 100_000_000},  # tổng 300tr ≠ 500tr
            ]
        )
        db = AsyncMock()
        db.scalar.side_effect = [proposal, None]

        with pytest.raises(BusinessRuleError) as err:
            await ProposalsService(db=db).transition_status(
                proposal.owner_user_id, proposal.id, "sent"
            )

        # Câu lỗi phải nêu CẢ HAI con số, không chỉ nói "sai".
        assert "300" in str(err.value) and "500" in str(err.value)

    async def test_cho_gui_khi_tong_khop(self) -> None:
        proposal = self._proposal_with(
            [
                {"label": "Backend", "amount": 300_000_000},
                {"label": "Frontend", "amount": 200_000_000},  # đúng 500tr
            ]
        )
        db = AsyncMock()
        db.scalar.side_effect = [proposal, None]

        with patch("src.modules.proposals.application.service.event_bus") as bus:
            bus.publish = AsyncMock()
            result = await ProposalsService(db=db).transition_status(
                proposal.owner_user_id, proposal.id, "sent"
            )

        assert result.status == "sent"

    async def test_khong_chan_dang_cu_chi_co_nhan(self) -> None:
        """Dạng cũ (chỉ nhãn) thì backend tự chia đều nên KHÔNG BAO GIỜ lệch — chặn là oan."""
        proposal = self._proposal_with(["Backend", "Frontend", "Kiem thu"])
        db = AsyncMock()
        db.scalar.side_effect = [proposal, None]

        with patch("src.modules.proposals.application.service.event_bus") as bus:
            bus.publish = AsyncMock()
            result = await ProposalsService(db=db).transition_status(
                proposal.owner_user_id, proposal.id, "sent"
            )

        assert result.status == "sent"
