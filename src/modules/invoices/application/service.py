"""Invoices application service."""

import secrets
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.exceptions.domain import BusinessRuleError, NotFoundError
from src.modules.invoices.schemas.request import InvoiceRequest


@dataclass
class InvoicesService:
    db: AsyncSession

    async def _get_invoice(self, user_id: uuid.UUID, invoice_id: uuid.UUID):  # type: ignore[return]
        from src.infrastructure.database.models import InvoiceModel

        invoice = await self.db.scalar(
            select(InvoiceModel).where(
                InvoiceModel.id == invoice_id,
                InvoiceModel.owner_user_id == user_id,
            )
        )
        if invoice is None:
            raise NotFoundError(f"Invoice {invoice_id} not found")
        return invoice

    async def create(self, user_id: uuid.UUID, payload: InvoiceRequest):  # type: ignore[return]
        from src.infrastructure.database.models import InvoiceModel

        if payload.deal_id is None:
            raise BusinessRuleError("Invoice must be linked to a deal or contract")

        tax_amount = payload.subtotal * payload.tax_rate
        total = payload.subtotal + tax_amount
        invoice_number = f"INV-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{secrets.token_hex(2).upper()}"

        invoice = InvoiceModel(
            owner_user_id=user_id,
            client_id=payload.client_id,
            deal_id=payload.deal_id,
            invoice_number=invoice_number,
            status="draft",
            issue_date=date.today(),
            due_date=payload.due_date,
            currency=payload.currency,
            subtotal=payload.subtotal,
            tax_rate=payload.tax_rate,
            tax_amount=tax_amount,
            total=total,
            amount_paid=0,
            notes=payload.notes,
            client_snapshot={},
        )
        self.db.add(invoice)
        await self.db.flush()
        await self.db.refresh(invoice)
        return invoice

    async def list_all(self, user_id: uuid.UUID) -> list:
        from src.infrastructure.database.models import InvoiceModel

        result = await self.db.execute(
            select(InvoiceModel).where(InvoiceModel.owner_user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_one(self, user_id: uuid.UUID, invoice_id: uuid.UUID):  # type: ignore[return]
        return await self._get_invoice(user_id, invoice_id)

    async def update(self, user_id: uuid.UUID, invoice_id: uuid.UUID, payload: InvoiceRequest):  # type: ignore[return]
        invoice = await self._get_invoice(user_id, invoice_id)
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
        await self.db.flush()
        await self.db.refresh(invoice)
        return invoice

    async def delete(self, user_id: uuid.UUID, invoice_id: uuid.UUID) -> None:
        invoice = await self._get_invoice(user_id, invoice_id)
        await self.db.delete(invoice)
        await self.db.flush()
