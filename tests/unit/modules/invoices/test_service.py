import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.modules.invoices.application.service import InvoicesService
from src.modules.invoices.schemas.request import InvoiceRequest, InvoiceUpdateRequest, PaymentRequest
from src.shared.exceptions.domain import BusinessRuleError, NotFoundError


@dataclass
class InvoiceStub:
    id: uuid.UUID
    status: str = "draft"
    amount_paid: Decimal = Decimal("0")
    total: Decimal = Decimal("100")
    subtotal: Decimal = Decimal("100")
    tax_rate: Decimal = Decimal("0")
    tax_amount: Decimal = Decimal("0")
    due_date: date = date(2026, 1, 31)
    notes: str | None = None
    sent_at: object | None = None
    voided_at: object | None = None


def invoice_request(**overrides) -> InvoiceRequest:
    data = {
        "client_id": uuid.uuid4(),
        "deal_id": uuid.uuid4(),
        "subtotal": Decimal("100"),
        "due_date": date(2026, 1, 31),
    }
    data.update(overrides)
    return InvoiceRequest(**data)


async def test_create_allows_contract_only_invoice() -> None:
    repo = AsyncMock()
    repo.get_client_by_id.return_value = object()
    repo.get_contract_by_id.return_value = object()
    repo.create.return_value = InvoiceStub(id=uuid.uuid4())
    repo.save.side_effect = lambda invoice: invoice
    service = InvoicesService(db=AsyncMock(), repo=repo)

    result = await service.create(uuid.uuid4(), invoice_request(deal_id=None, contract_id=uuid.uuid4()))

    assert result.status == "draft"


async def test_create_rejects_unowned_client() -> None:
    repo = AsyncMock()
    repo.get_client_by_id.return_value = None
    service = InvoicesService(db=AsyncMock(), repo=repo)

    with pytest.raises(NotFoundError):
        await service.create(uuid.uuid4(), invoice_request())


async def test_update_is_draft_only() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = InvoiceStub(id=uuid.uuid4(), status="sent")
    service = InvoicesService(db=AsyncMock(), repo=repo)

    with pytest.raises(BusinessRuleError):
        await service.update(uuid.uuid4(), uuid.uuid4(), InvoiceUpdateRequest(notes="x"))


async def test_void_blocks_recorded_payment() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = InvoiceStub(id=uuid.uuid4(), status="partially_paid", amount_paid=Decimal("1"))
    service = InvoicesService(db=AsyncMock(), repo=repo)

    with pytest.raises(BusinessRuleError):
        await service.void(uuid.uuid4(), uuid.uuid4())


async def test_record_payment_rejects_non_positive_amount() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = InvoiceStub(id=uuid.uuid4(), status="sent")
    service = InvoicesService(db=AsyncMock(), repo=repo)

    with pytest.raises(BusinessRuleError):
        await service.record_payment(uuid.uuid4(), uuid.uuid4(), PaymentRequest.model_construct(amount=Decimal("0"), payment_date=date(2026, 1, 1), payment_method="other"))


async def test_get_public_view_returns_invoice() -> None:
    invoice = InvoiceStub(id=uuid.uuid4(), status="sent")
    repo = AsyncMock()
    repo.get_public_by_token.return_value = invoice
    service = InvoicesService(db=AsyncMock(), repo=repo)

    result = await service.get_public_view("some_token")

    assert result.status == "sent"


async def test_get_public_view_raises_for_invalid_token() -> None:
    repo = AsyncMock()
    repo.get_public_by_token.return_value = None
    service = InvoicesService(db=AsyncMock(), repo=repo)

    with pytest.raises(NotFoundError):
        await service.get_public_view("bad_token")
