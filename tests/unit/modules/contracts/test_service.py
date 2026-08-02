"""Unit tests for ContractsService."""

import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.modules.contracts.application.service import ContractsService
from src.modules.contracts.schemas.request import CreateContractRequest, UpdateContractRequest
from src.modules.tasks.schemas.request import CreateTaskRequest
from src.shared.exceptions.domain import (
    BusinessRuleError,
    EntitlementError,
    InvalidStateTransitionError,
    NotFoundError,
)


@contextmanager
def _payment_task_wiring(payloads: list[CreateTaskRequest] | None = None):
    """Giả lập ba collaborator mà việc GHI NHẬN ĐÃ KÝ kéo theo: tạo project cho deal, lấy mốc
    thanh toán của báo giá đã chốt, và sinh task "Thu tiền:".

    Ba thứ đó được import CỤC BỘ bên trong `transition_status` (tránh vòng import), nên phải
    patch tại chính module gốc chứ không phải chỗ dùng.  #Huynh
    """
    project = MagicMock()
    project.id = uuid.uuid4()
    create_many = AsyncMock(return_value=[])
    get_or_create = AsyncMock(return_value=project)
    with (
        patch("src.modules.projects.application.service.ProjectService") as project_service,
        patch(
            "src.modules.proposals.application.service.payment_task_payloads_for_deal",
            AsyncMock(return_value=payloads if payloads is not None else []),
        ),
        patch("src.modules.tasks.application.service.TaskService") as task_service,
    ):
        project_service.return_value.get_or_create_for_deal = get_or_create
        task_service.return_value.create_many_for_entity = create_many
        yield SimpleNamespace(
            project=project, get_or_create=get_or_create, create_many=create_many
        )


def _make_contract(**kwargs) -> MagicMock:
    m = MagicMock()
    m.id = kwargs.get("id", uuid.uuid4())
    m.deal_id = kwargs.get("deal_id", uuid.uuid4())
    m.proposal_id = kwargs.get("proposal_id", uuid.uuid4())
    m.client_id = kwargs.get("client_id", uuid.uuid4())
    m.owner_user_id = kwargs.get("owner_user_id", uuid.uuid4())
    m.status = kwargs.get("status", "draft")
    m.signed_by_freelancer_at = None
    return m


def _make_proposal(**kwargs) -> MagicMock:
    m = MagicMock()
    m.id = kwargs.get("id", uuid.uuid4())
    m.status = kwargs.get("status", "accepted")
    m.owner_user_id = kwargs.get("owner_user_id", uuid.uuid4())
    m.deal_id = kwargs.get("deal_id", uuid.uuid4())
    return m


def _make_deal(**kwargs) -> MagicMock:
    m = MagicMock()
    m.id = kwargs.get("id", uuid.uuid4())
    m.client_id = kwargs.get("client_id", uuid.uuid4())
    return m


def _make_plan(**kwargs) -> MagicMock:
    m = MagicMock()
    m.can_export_pdf = kwargs.get("can_export_pdf", True)
    return m


def _make_sub(**kwargs) -> MagicMock:
    m = MagicMock()
    m.plan_id = kwargs.get("plan_id", uuid.uuid4())
    return m


def _make_create_payload(**kwargs) -> CreateContractRequest:
    return CreateContractRequest(
        proposal_id=kwargs.get("proposal_id", uuid.uuid4()),
        content=kwargs.get("content", {}),
    )


def _make_update_payload(**kwargs) -> UpdateContractRequest:
    return UpdateContractRequest(
        content=kwargs.get("content"),
        effective_date=kwargs.get("effective_date"),
        end_date=kwargs.get("end_date"),
    )


class TestCreate:
    async def test_raises_if_proposal_not_found(self) -> None:
        db = AsyncMock()
        db.scalar.return_value = None

        with pytest.raises(NotFoundError, match="Proposal"):
            await ContractsService(db=db).create(uuid.uuid4(), _make_create_payload())

    async def test_raises_if_proposal_belongs_to_another_user(self) -> None:
        proposal = _make_proposal(status="accepted", owner_user_id=uuid.uuid4())
        db = AsyncMock()
        db.scalar.return_value = proposal

        with pytest.raises(NotFoundError, match="Proposal"):
            await ContractsService(db=db).create(uuid.uuid4(), _make_create_payload())

    async def test_raises_if_proposal_not_accepted(self) -> None:
        user_id = uuid.uuid4()
        proposal = _make_proposal(status="draft", owner_user_id=user_id)
        db = AsyncMock()
        db.scalar.return_value = proposal

        with pytest.raises(BusinessRuleError, match="accepted proposal"):
            await ContractsService(db=db).create(user_id, _make_create_payload())

    async def test_creates_from_accepted_proposal(self) -> None:
        user_id = uuid.uuid4()
        proposal = _make_proposal(status="accepted", owner_user_id=user_id)
        deal = _make_deal()
        client = MagicMock(id=uuid.uuid4(), name="Acme", email="a@b.com", phone=None)
        db = AsyncMock()
        db.add = MagicMock()  # session.add() is synchronous
        db.scalar.side_effect = [proposal, deal, 0, client]

        await ContractsService(db=db).create(user_id, _make_create_payload())

        db.add.assert_called_once()
        db.flush.assert_called_once()


class TestTransitionStatus:
    async def test_draft_to_pending_signatures(self) -> None:
        contract = _make_contract(status="draft")
        db = AsyncMock()
        db.scalar.return_value = contract

        result = await ContractsService(db=db).transition_status(
            contract.owner_user_id, contract.id, "pending_signatures"
        )
        assert result.status == "pending_signatures"

    async def test_pending_to_active_sets_signed_at(self) -> None:
        contract = _make_contract(status="pending_signatures")
        db = AsyncMock()
        db.scalar.return_value = contract

        with _payment_task_wiring():
            result = await ContractsService(db=db).transition_status(
                contract.owner_user_id, contract.id, "active"
            )
        assert result.status == "active"
        assert result.signed_by_freelancer_at is not None

    async def test_ghi_nhan_da_ky_thi_sinh_task_thu_tien_ngay(self) -> None:
        """Ký xong là phải thấy ngay mốc thu tiền.

        Mốc đợt 1 của mọi báo giá ghi "Khi ký hợp đồng / trước khi bắt đầu". Trước đây task
        "Thu tiền:" chỉ sinh khi deal chuyển "active" (bấm "Bắt đầu triển khai") — tức MỘT
        NHỊP SAU thời điểm phải thu: đã bắt tay làm rồi hệ thống mới nhắc đi đòi cọc.  #Huynh
        """
        contract = _make_contract(status="pending_signatures")
        db = AsyncMock()
        db.scalar.return_value = contract
        payloads = [
            CreateTaskRequest(title="Thu tiền: Đặt cọc khi ký hợp đồng"),
            CreateTaskRequest(title="Thu tiền: Thanh toán khi nghiệm thu & bàn giao"),
        ]

        with _payment_task_wiring(payloads) as wiring:
            await ContractsService(db=db).transition_status(
                contract.owner_user_id, contract.id, "active"
            )

        wiring.get_or_create.assert_awaited_once()
        # Task gắn vào PROJECT, không phải contract — bảng "Công việc" hiển thị theo project.
        wiring.create_many.assert_awaited_once_with(
            "project", wiring.project.id, contract.owner_user_id, payloads
        )

    async def test_khong_co_moc_thi_khong_tao_task(self) -> None:
        # Báo giá chưa chốt / không có mốc nào -> không đẻ ra task rỗng.
        contract = _make_contract(status="pending_signatures")
        db = AsyncMock()
        db.scalar.return_value = contract

        with _payment_task_wiring([]) as wiring:
            await ContractsService(db=db).transition_status(
                contract.owner_user_id, contract.id, "active"
            )

        wiring.create_many.assert_not_awaited()

    async def test_invalid_transition_raises(self) -> None:
        contract = _make_contract(status="draft")
        db = AsyncMock()
        db.scalar.return_value = contract

        with pytest.raises(InvalidStateTransitionError):
            await ContractsService(db=db).transition_status(
                contract.owner_user_id, contract.id, "completed"
            )

    async def test_unknown_status_raises_business_rule(self) -> None:
        contract = _make_contract(status="draft")
        db = AsyncMock()
        db.scalar.return_value = contract

        with pytest.raises(BusinessRuleError, match="not a valid contract status"):
            await ContractsService(db=db).transition_status(
                contract.owner_user_id, contract.id, "bogus"
            )

    async def test_not_found_raises(self) -> None:
        db = AsyncMock()
        db.scalar.return_value = None

        with pytest.raises(NotFoundError):
            await ContractsService(db=db).transition_status(
                uuid.uuid4(), uuid.uuid4(), "pending_signatures"
            )


class TestExportPdf:
    async def test_raises_without_subscription(self) -> None:
        contract = _make_contract()
        db = AsyncMock()
        db.scalar.side_effect = [contract, None]

        with pytest.raises(EntitlementError):
            await ContractsService(db=db).export_pdf(contract.owner_user_id, contract.id)

    async def test_raises_when_plan_disallows_pdf(self) -> None:
        contract = _make_contract()
        sub = _make_sub()
        plan = _make_plan(can_export_pdf=False)
        db = AsyncMock()
        db.scalar.side_effect = [contract, sub, plan]

        with pytest.raises(EntitlementError, match="PDF export"):
            await ContractsService(db=db).export_pdf(contract.owner_user_id, contract.id)

    async def test_queues_task_and_returns_pending(self) -> None:
        contract = _make_contract()
        sub = _make_sub()
        plan = _make_plan(can_export_pdf=True)
        db = AsyncMock()
        db.scalar.side_effect = [contract, sub, plan]

        mock_task = MagicMock(id="celery-task-id-123")
        with patch("src.workers.pdf_jobs.tasks.render_contract_pdf") as mock_fn:
            mock_fn.delay.return_value = mock_task
            result = await ContractsService(db=db).export_pdf(contract.owner_user_id, contract.id)

        assert result["status"] == "pending"
        assert result["task_id"] == "celery-task-id-123"
        mock_fn.delay.assert_called_once_with(str(contract.id))

    async def test_not_found_raises(self) -> None:
        db = AsyncMock()
        db.scalar.return_value = None

        with pytest.raises(NotFoundError):
            await ContractsService(db=db).export_pdf(uuid.uuid4(), uuid.uuid4())


class TestDelete:
    async def test_deletes_draft(self) -> None:
        contract = _make_contract(status="draft")
        db = AsyncMock()
        db.scalar.return_value = contract

        await ContractsService(db=db).delete(contract.owner_user_id, contract.id)
        db.delete.assert_awaited_once_with(contract)

    async def test_deletes_expired(self) -> None:
        contract = _make_contract(status="expired")
        db = AsyncMock()
        db.scalar.return_value = contract

        await ContractsService(db=db).delete(contract.owner_user_id, contract.id)
        db.delete.assert_awaited_once_with(contract)

    async def test_raises_for_active_contract(self) -> None:
        contract = _make_contract(status="active")
        db = AsyncMock()
        db.scalar.return_value = contract

        with pytest.raises(BusinessRuleError, match="draft or expired"):
            await ContractsService(db=db).delete(contract.owner_user_id, contract.id)

    async def test_raises_for_pending_signatures(self) -> None:
        contract = _make_contract(status="pending_signatures")
        db = AsyncMock()
        db.scalar.return_value = contract

        with pytest.raises(BusinessRuleError):
            await ContractsService(db=db).delete(contract.owner_user_id, contract.id)

    async def test_not_found_raises(self) -> None:
        db = AsyncMock()
        db.scalar.return_value = None

        with pytest.raises(NotFoundError):
            await ContractsService(db=db).delete(uuid.uuid4(), uuid.uuid4())


class TestUpdate:
    async def test_raises_when_not_draft(self) -> None:
        contract = _make_contract(status="active")
        db = AsyncMock()
        db.scalar.return_value = contract

        with pytest.raises(BusinessRuleError, match="draft status"):
            await ContractsService(db=db).update(
                contract.owner_user_id, contract.id, _make_update_payload()
            )


class TestApplyChosenTemplate:
    """Chèn điều khoản từ mẫu freelancer CHỌN, NGUYÊN VĂN. AI không đụng tới."""

    def _service(self, template):  # type: ignore[no-untyped-def]
        repo = AsyncMock()
        repo.get_template_for_use.return_value = template
        return ContractsService(db=AsyncMock(), repo=repo), repo

    async def test_khong_chon_thi_khong_chen(self) -> None:
        """template_id=None ("AI tự viết") → không tra, không chèn."""
        service, repo = self._service(MagicMock())

        result = await service._apply_chosen_template(
            {"x": 1}, None, MagicMock(profession="ui-ux-design"), template_type="contract"
        )

        assert "standard_terms" not in result
        repo.get_template_for_use.assert_not_awaited()

    async def test_chon_mau_hop_le_chen_nguyen_van(self) -> None:
        tid = uuid.uuid4()
        template = MagicMock(content={"body": "Bàn giao file nguồn sau thanh toán đủ."})
        service, repo = self._service(template)

        result = await service._apply_chosen_template(
            {"scope_of_work": "..."},
            tid,
            MagicMock(profession="ui-ux-design"),
            template_type="contract",
        )

        assert result["standard_terms"] == "Bàn giao file nguồn sau thanh toán đủ."
        assert result["scope_of_work"] == "..."  # AI sinh gì vẫn giữ, chỉ THÊM
        # Tra theo đúng id + nghề của freelancer (chặn mượn mẫu nghề khác).
        assert repo.get_template_for_use.await_args.args[0] == tid
        assert repo.get_template_for_use.await_args.kwargs["profession"] == "ui-ux-design"

    async def test_mau_khong_dung_duoc_thi_bao_loi(self) -> None:
        """Mẫu đã tắt / nghề khác / không tồn tại → repo trả None → chặn, không im lặng."""
        from src.shared.exceptions.domain import ValidationError

        service, _ = self._service(None)

        with pytest.raises(ValidationError):
            await service._apply_chosen_template(
                {}, uuid.uuid4(), MagicMock(profession="graphic-design"), template_type="contract"
            )

    async def test_mau_body_rong_thi_khong_chen(self) -> None:
        service, _ = self._service(MagicMock(content={"body": "   "}))

        result = await service._apply_chosen_template(
            {}, uuid.uuid4(), MagicMock(profession=None), template_type="contract"
        )

        assert "standard_terms" not in result
