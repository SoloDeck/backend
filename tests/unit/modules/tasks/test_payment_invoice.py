"""Unit tests cho `create_invoice_for_payment_task` (mock hết, không chạm DB).

Trọng tâm: idempotency của nút "Soạn & gửi hóa đơn" phải chốt theo hóa đơn CÒN SỐNG.
Hóa đơn đã huỷ thì không gửi lại được, không ghi nhận thanh toán được — giữ nó làm mốc
idempotency là khoá vĩnh viễn khoản phải thu đó.  #Huynh
"""

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.modules.tasks.application.payment_invoice import create_invoice_for_payment_task


def _task_stub(invoice_id: uuid.UUID | None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        entity_type="project",
        entity_id=uuid.uuid4(),
        title="Dựng giao diện",
        billing_amount=Decimal("12000000"),
        invoice_id=invoice_id,
    )


def _invoice_stub(status: str) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), status=status)


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    task: SimpleNamespace,
    existing: SimpleNamespace | None,
    moi: SimpleNamespace,
) -> tuple[AsyncMock, SimpleNamespace, SimpleNamespace]:
    """Thay TaskService / InvoicesRepository / InvoicesService bằng mock.

    `payment_invoice` import ba thứ này BÊN TRONG hàm, nên vá ở module gốc là đủ.
    """
    task_service = SimpleNamespace(
        _get_owned_task=AsyncMock(return_value=task),
        repo=SimpleNamespace(save=AsyncMock()),
    )
    monkeypatch.setattr(
        "src.modules.tasks.application.service.TaskService", lambda db: task_service
    )

    deal = SimpleNamespace(id=uuid.uuid4(), client_id=uuid.uuid4())
    invoices_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=existing),
        get_deal_by_id=AsyncMock(return_value=deal),
    )
    monkeypatch.setattr(
        "src.modules.invoices.infrastructure.repository.InvoicesRepository",
        lambda db: invoices_repo,
    )

    invoices_service = SimpleNamespace(create=AsyncMock(return_value=moi))
    monkeypatch.setattr(
        "src.modules.invoices.application.service.InvoicesService",
        lambda **kwargs: invoices_service,
    )

    db = AsyncMock()
    db.get.return_value = SimpleNamespace(deal_id=deal.id)
    return db, invoices_service, task_service


async def test_hoa_don_con_song_thi_khong_tao_cai_thu_hai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bấm hai lần vẫn ra đúng một hóa đơn — hành vi cũ phải giữ nguyên."""
    dang_co = _invoice_stub("draft")
    task = _task_stub(invoice_id=dang_co.id)
    db, invoices_service, _ = _wire(monkeypatch, task, dang_co, _invoice_stub("draft"))

    ket_qua = await create_invoice_for_payment_task(db, task.id, uuid.uuid4())

    assert ket_qua is dang_co
    invoices_service.create.assert_not_awaited()


async def test_huy_hoa_don_roi_thi_xuat_lai_duoc(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gửi nhầm số tiền → huỷ hóa đơn → phải soạn lại được cái mới.

    Bản cũ trả về chính hóa đơn đã huỷ, mà hóa đơn `void` thì không gửi được cũng không
    ghi nhận thanh toán được — khoản tiền đó mắc kẹt vĩnh viễn.
    """
    da_huy = _invoice_stub("void")
    hoa_don_moi = _invoice_stub("draft")
    task = _task_stub(invoice_id=da_huy.id)
    db, invoices_service, task_service = _wire(monkeypatch, task, da_huy, hoa_don_moi)

    ket_qua = await create_invoice_for_payment_task(db, task.id, uuid.uuid4())

    assert ket_qua is hoa_don_moi
    invoices_service.create.assert_awaited_once()
    # Mốc thu tiền phải trỏ sang hóa đơn mới, không còn dính hóa đơn đã huỷ.
    assert task.invoice_id == hoa_don_moi.id
    task_service.repo.save.assert_awaited_once()
