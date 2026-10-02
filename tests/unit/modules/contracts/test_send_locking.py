"""`ContractsService.send` — khoá deal → hợp đồng (không đứng chờ) và luật "mỗi deal một hợp đồng sống".

Repo là bản giả nên bài test ghi lại được THỨ TỰ các việc. Chỉ mục `uq_contracts_one_active_per_deal`
thật được thử ở `tests/integration/.../test_send_email.py` (có Postgres thật).
"""

import uuid
from collections.abc import Callable, Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.modules.contracts.application.service import ContractsService
from src.modules.contracts.infrastructure.repository import LiveContractExistsError, RowLockedError
from src.modules.contracts.schemas.request import UpdateContractRequest
from src.shared.exceptions.domain import BusinessRuleError, EmailDeliveryError, NotFoundError
from tests.unit.modules.contracts.test_service import _make_contract

SEND_EMAIL = "src.shared.email.smtp.send_email"
PDF_RENDERER = "src.ai.contract_generator.application.render.ContractPdfRenderer"


class Harness:
    """Service + repo giả, và một danh sách `calls` ghi lại việc nào xảy ra TRƯỚC việc nào."""

    send_email: AsyncMock

    def __init__(self, *, status: str = "draft") -> None:
        self.user_id = uuid.uuid4()
        self.contract = _make_contract(status=status, owner_user_id=self.user_id)
        self.calls: list[str] = []

        repo = AsyncMock()
        repo.get_by_id.return_value = self.contract
        repo.get_deal_for_update.side_effect = self._lock("khoa_deal", SimpleNamespace())
        repo.get_by_id_for_update.side_effect = self._lock("khoa_hop_dong", self.contract)
        repo.get_live_contract_for_deal.return_value = None
        repo.get_client.return_value = SimpleNamespace(
            name="Công ty Nắng", email="khach@example.com"
        )
        repo.get_user.return_value = SimpleNamespace(
            full_name="Huỳnh Hòa", email="hoa@example.com"
        )
        repo.save.side_effect = lambda obj: obj
        repo.save_entering_live_status.side_effect = lambda obj: obj
        self.repo = repo
        self.service = ContractsService(db=AsyncMock(), repo=repo)

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
    harness = Harness()
    document = SimpleNamespace(project_name="Web cà phê", contract_number="HD-20261001-01")
    with (
        patch.object(ContractsService, "_build_document", AsyncMock(return_value=document)),
        patch(PDF_RENDERER) as renderer,
        patch(SEND_EMAIL, new=AsyncMock(side_effect=harness.record("gui_thu"))) as send_email,
    ):
        renderer.return_value.render_pdf.return_value = b"%PDF-1.4 gia"
        harness.send_email = send_email
        yield harness


class TestSendKhoaDealTruocHopDongSau:
    async def test_khoa_deal_roi_moi_khoa_hop_dong_va_ca_hai_deu_nowait(self, h: Harness) -> None:
        await h.service.send(h.user_id, h.contract.id)

        assert h.calls == [
            "khoa_deal(nowait=True)",
            "khoa_hop_dong(nowait=True)",
            "gui_thu",
        ]

    async def test_chot_trang_thai_cho_ky_roi_moi_gui_thu(self, h: Harness) -> None:
        result = await h.service.send(h.user_id, h.contract.id)

        assert result.status == "pending_signatures"
        h.repo.save_entering_live_status.assert_awaited_once_with(h.contract)

    async def test_deal_dang_bi_giu_thi_409_ngay_va_khong_dong_toi_gi_nua(
        self, h: Harness
    ) -> None:
        h.repo.get_deal_for_update.side_effect = RowLockedError()

        with pytest.raises(BusinessRuleError, match="đang được gửi hoặc đang lưu"):
            await h.service.send(h.user_id, h.contract.id)

        h.repo.get_by_id_for_update.assert_not_awaited()
        h.send_email.assert_not_awaited()
        h.repo.save_entering_live_status.assert_not_awaited()

    async def test_hop_dong_dang_bi_giu_thi_409_ngay_va_khong_gui_thu(self, h: Harness) -> None:
        h.repo.get_by_id_for_update.side_effect = RowLockedError()

        with pytest.raises(BusinessRuleError, match="Đợi vài giây rồi thử lại"):
            await h.service.send(h.user_id, h.contract.id)

        h.send_email.assert_not_awaited()
        assert h.contract.status == "draft"

    async def test_hop_dong_khong_co_that_thi_404_va_khong_khoa_gi(self, h: Harness) -> None:
        h.repo.get_by_id.return_value = None

        with pytest.raises(NotFoundError):
            await h.service.send(h.user_id, h.contract.id)

        h.repo.get_deal_for_update.assert_not_awaited()
        h.repo.get_by_id_for_update.assert_not_awaited()

    async def test_hop_dong_bi_xoa_giua_luc_doc_va_khoa_thi_404(self, h: Harness) -> None:
        h.repo.get_by_id_for_update.side_effect = h._lock("khoa_hop_dong", None)

        with pytest.raises(NotFoundError):
            await h.service.send(h.user_id, h.contract.id)

        h.send_email.assert_not_awaited()

    async def test_da_gui_roi_thi_noi_chi_hop_dong_nhap_moi_gui_duoc(self, h: Harness) -> None:
        """Gửi TUẦN TỰ lần hai (lượt trước đã commit) ra đúng câu cũ, không phải câu "đang bận"."""
        h.contract.status = "pending_signatures"

        with pytest.raises(BusinessRuleError, match="Chỉ hợp đồng nháp mới gửi được"):
            await h.service.send(h.user_id, h.contract.id)

        h.send_email.assert_not_awaited()

    async def test_trang_thai_duoc_doc_lai_sau_khi_giu_khoa_chu_khong_dung_ban_doc_truoc(
        self, h: Harness
    ) -> None:
        stale = _make_contract(status="draft", owner_user_id=h.user_id)
        fresh = _make_contract(status="pending_signatures", owner_user_id=h.user_id)
        h.repo.get_by_id.return_value = stale
        h.repo.get_by_id_for_update.side_effect = h._lock("khoa_hop_dong", fresh)

        with pytest.raises(BusinessRuleError, match="Chỉ hợp đồng nháp mới gửi được"):
            await h.service.send(h.user_id, stale.id)

        h.send_email.assert_not_awaited()

    async def test_thu_hong_thi_van_nem_loi_ra_de_route_rollback(self, h: Harness) -> None:
        h.send_email.side_effect = EmailDeliveryError("Hộp thư hệ thống đang hỏng.", "auth")

        with pytest.raises(EmailDeliveryError):
            await h.service.send(h.user_id, h.contract.id)


class TestMoiDealMotHopDongSong:
    """Chỉ mục `uq_contracts_one_active_per_deal`: mỗi deal tối đa MỘT hợp đồng chờ ký / đang
    hiệu lực. Chạm vào nó mà không bắt thì ra 500 kèm `IntegrityError` trần."""

    async def test_deal_da_co_hop_dong_khac_dang_cho_ky_thi_409_gon(self, h: Harness) -> None:
        h.repo.get_live_contract_for_deal.return_value = _make_contract(
            status="pending_signatures"
        )

        with pytest.raises(BusinessRuleError, match="hợp đồng khác đang chờ khách ký"):
            await h.service.send(h.user_id, h.contract.id)

        # Hỏi TRƯỚC khi chốt trạng thái hay gửi thư: không có thư nào bay đi rồi mới biết.
        h.repo.save_entering_live_status.assert_not_awaited()
        h.send_email.assert_not_awaited()
        assert h.contract.status == "draft"

    async def test_cau_hoi_loai_chinh_hop_dong_dang_gui_ra(self, h: Harness) -> None:
        await h.service.send(h.user_id, h.contract.id)

        h.repo.get_live_contract_for_deal.assert_awaited_once_with(
            h.contract.deal_id, h.contract.id
        )

    async def test_cau_hoi_nam_sau_khoa_va_truoc_khi_gui(self, h: Harness) -> None:
        h.repo.get_live_contract_for_deal.side_effect = h.record("hoi_hop_dong_song")

        await h.service.send(h.user_id, h.contract.id)

        assert h.calls == [
            "khoa_deal(nowait=True)",
            "khoa_hop_dong(nowait=True)",
            "hoi_hop_dong_song",
            "gui_thu",
        ]

    async def test_luoi_an_toan_chi_muc_tu_choi_thi_van_ra_409_chu_khong_phai_500(
        self, h: Harness
    ) -> None:
        """`PATCH .../status` đi thẳng vào `transition_status`, không qua câu hỏi ở `send` và
        không khoá deal — hai lượt ghi nhận cùng lúc vẫn có thể để chỉ mục từ chối."""
        h.repo.save_entering_live_status.side_effect = LiveContractExistsError()

        with pytest.raises(BusinessRuleError, match="hợp đồng khác đang chờ khách ký"):
            await h.service.transition_status(h.user_id, h.contract.id, "pending_signatures")

    async def test_chi_chuyen_sang_cho_ky_moi_di_qua_cua_kiem_tra_chi_muc(
        self, h: Harness
    ) -> None:
        """Các chuyển trạng thái khác không thể đẩy hợp đồng vào chỗ chỉ mục canh giữ."""
        h.contract.status = "pending_signatures"
        h.contract.signed_by_freelancer_at = None
        h.contract.signed_by_client_at = None
        h.repo.has_accepted_proposal.return_value = True

        with patch.object(ContractsService, "_apply_active_side_effects", AsyncMock()):
            await h.service.transition_status(h.user_id, h.contract.id, "active")

        h.repo.save_entering_live_status.assert_not_awaited()
        h.repo.save.assert_awaited_once_with(h.contract)


class TestSuaNoiDungKhongDungNowait:
    async def test_update_cho_khoa_chu_khong_that_bai_va_khong_khoa_deal(self, h: Harness) -> None:
        """Hai lượt tự lưu liên tiếp phải XẾP HÀNG, không được thất bại."""
        await h.service.update(
            h.user_id, h.contract.id, UpdateContractRequest(content={"title": "x"})
        )

        h.repo.get_by_id_for_update.assert_awaited_once_with(h.contract.id, h.user_id)
        h.repo.get_deal_for_update.assert_not_awaited()

    async def test_milestone_cung_cho_khoa_chu_khong_that_bai(self, h: Harness) -> None:
        h.repo.create_milestone.return_value = MagicMock()

        await h.service.add_milestone(
            h.user_id,
            h.contract.id,
            SimpleNamespace(description="Cọc", amount=1, due_date=None, sort_order=0),  # type: ignore[arg-type]
        )

        h.repo.get_by_id_for_update.assert_awaited_once_with(h.contract.id, h.user_id)
        h.repo.get_deal_for_update.assert_not_awaited()
