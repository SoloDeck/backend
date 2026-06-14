"""Invoices application service."""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.invoices.infrastructure.repository import InvoicesRepository
from src.modules.invoices.schemas.request import InvoiceRequest, InvoiceUpdateRequest, PaymentRequest
from src.shared.exceptions.domain import BusinessRuleError, NotFoundError


@dataclass
class InvoicesService:
    db: AsyncSession
    repo: InvoicesRepository | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = InvoicesRepository(self.db)

    async def _get_invoice(self, user_id: uuid.UUID, invoice_id: uuid.UUID):  # type: ignore[return]
        invoice = await self.repo.get_by_id(invoice_id, user_id)
        if invoice is None:
            raise NotFoundError(f"Invoice {invoice_id} not found")
        return invoice

    async def create(self, user_id: uuid.UUID, payload: InvoiceRequest):  # type: ignore[return]
        if payload.deal_id is None and payload.contract_id is None:
            raise BusinessRuleError("Invoice must be linked to a deal or contract")
        client = await self.repo.get_client_by_id(payload.client_id, user_id)
        if client is None:
            raise NotFoundError(f"Client {payload.client_id} not found")
        if payload.deal_id is not None and await self.repo.get_deal_by_id(payload.deal_id, user_id) is None:
            raise NotFoundError(f"Deal {payload.deal_id} not found")
        if payload.contract_id is not None and await self.repo.get_contract_by_id(payload.contract_id, user_id) is None:
            raise NotFoundError(f"Contract {payload.contract_id} not found")

        subtotal = payload.subtotal
        if subtotal is None:
            if not payload.line_items:
                raise BusinessRuleError("Invoice requires subtotal or line_items")
            subtotal = sum((i.quantity * i.unit_price for i in payload.line_items), Decimal("0"))
        if subtotal <= 0:
            raise BusinessRuleError("Invoice subtotal must be greater than zero")
        tax_amount = subtotal * payload.tax_rate
        total = subtotal + tax_amount
        invoice_number = (
            f"INV-{datetime.now(UTC).strftime('%Y%m%d')}-{secrets.token_hex(2).upper()}"
        )

        invoice = await self.repo.create(
            owner_user_id=user_id,
            client_id=payload.client_id,
            contract_id=payload.contract_id,
            deal_id=payload.deal_id,
            invoice_number=invoice_number,
            status="draft",
            issue_date=payload.issue_date or date.today(),
            due_date=payload.due_date,
            currency=payload.currency,
            subtotal=subtotal,
            tax_rate=payload.tax_rate,
            tax_amount=tax_amount,
            total=total,
            amount_paid=0,
            notes=payload.notes,
            client_snapshot={},
        )
        for item in payload.line_items or []:
            await self.repo.add_line_item(invoice_id=invoice.id, description=item.description, quantity=item.quantity, unit_price=item.unit_price, amount=item.quantity * item.unit_price, sort_order=item.sort_order)
        return await self.repo.save(invoice)

    async def list_all(
        self,
        user_id: uuid.UUID,
        status: str | None = None,
        invoice_number: str | None = None,
    ) -> list:
        return await self.repo.list_all(user_id, status=status, invoice_number=invoice_number)

    async def get_one(self, user_id: uuid.UUID, invoice_id: uuid.UUID):  # type: ignore[return]
        return await self._get_invoice(user_id, invoice_id)

    async def update(self, user_id: uuid.UUID, invoice_id: uuid.UUID, payload: InvoiceUpdateRequest):  # type: ignore[return]
        invoice = await self._get_invoice(user_id, invoice_id)
        if invoice.status != "draft":
            raise BusinessRuleError("Only draft invoices can be updated")
        if payload.line_items:
            payload.subtotal = sum((i.quantity * i.unit_price for i in payload.line_items), Decimal("0"))
            await self.repo.replace_line_items(invoice_id, payload.line_items)
        if payload.subtotal is not None:
            invoice.subtotal = payload.subtotal
        if payload.tax_rate is not None:
            invoice.tax_rate = payload.tax_rate
        invoice.tax_amount = invoice.subtotal * invoice.tax_rate
        invoice.total = invoice.subtotal + invoice.tax_amount
        if payload.due_date is not None:
            invoice.due_date = payload.due_date
        if payload.notes is not None:
            invoice.notes = payload.notes
        return await self.repo.save(invoice)

    async def delete(self, user_id: uuid.UUID, invoice_id: uuid.UUID) -> None:
        invoice = await self._get_invoice(user_id, invoice_id)
        await self.repo.delete(invoice)

    async def send(self, user_id: uuid.UUID, invoice_id: uuid.UUID):
        invoice = await self._get_invoice(user_id, invoice_id)
        if invoice.status != "draft":
            raise BusinessRuleError("Only draft invoices can be sent")
        invoice.status = "sent"
        invoice.sent_at = datetime.now(UTC)
        invoice.share_token = secrets.token_urlsafe(32)
        return await self.repo.save(invoice)

    async def void(self, user_id: uuid.UUID, invoice_id: uuid.UUID):
        invoice = await self._get_invoice(user_id, invoice_id)
        if invoice.status == "void" or invoice.amount_paid > 0:
            raise BusinessRuleError("Invoices with recorded payments cannot be voided")
        invoice.status = "void"
        invoice.voided_at = datetime.now(UTC)
        return await self.repo.save(invoice)

    async def record_payment(self, user_id: uuid.UUID, invoice_id: uuid.UUID, payload: PaymentRequest):
        invoice = await self._get_invoice(user_id, invoice_id)
        if payload.amount <= 0:
            raise BusinessRuleError("Payment amount must be greater than zero")
        if invoice.status in ("draft", "void"):
            raise BusinessRuleError("Cannot record payment for draft or void invoice")
        if invoice.amount_paid + payload.amount > invoice.total:
            raise BusinessRuleError("Payment would exceed invoice total")
        await self.repo.add_payment(invoice_id=invoice_id, amount=payload.amount, payment_date=payload.payment_date, payment_method=payload.payment_method, reference_note=payload.reference_note)
        invoice.amount_paid += payload.amount
        invoice.status = "paid" if invoice.amount_paid == invoice.total else "partially_paid"
        return await self.repo.save(invoice)

    async def list_payments(self, user_id: uuid.UUID, invoice_id: uuid.UUID) -> list:
        await self._get_invoice(user_id, invoice_id)
        return await self.repo.list_payments(invoice_id)

    async def get_public_view(self, share_token: str):
        invoice = await self.repo.get_public_by_token(share_token)
        if invoice is None:
            raise NotFoundError("Invoice not found or link is invalid")
        return invoice
