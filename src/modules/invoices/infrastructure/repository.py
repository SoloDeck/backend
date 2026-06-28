import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import (
    ClientModel,
    ContractModel,
    DealModel,
    InvoiceLineItemModel,
    InvoiceModel,
    InvoicePaymentRecordModel,
)


@dataclass
class InvoicesRepository:
    db: AsyncSession

    async def get_by_id(self, invoice_id: uuid.UUID, owner_user_id: uuid.UUID):
        return await self.db.scalar(
            select(InvoiceModel).where(
                InvoiceModel.id == invoice_id, InvoiceModel.owner_user_id == owner_user_id
            )
        )

    async def get_public_by_token(self, share_token: str):
        return await self.db.scalar(
            select(InvoiceModel).where(
                InvoiceModel.share_token == share_token,
                InvoiceModel.status.notin_(["void"]),
            )
        )

    async def create(self, **values):
        invoice = InvoiceModel(**values)
        self.db.add(invoice)
        await self.db.flush()
        await self.db.refresh(invoice)
        return invoice

    async def get_client_by_id(self, client_id: uuid.UUID, owner_user_id: uuid.UUID):
        return await self.db.scalar(
            select(ClientModel).where(
                ClientModel.id == client_id,
                ClientModel.owner_user_id == owner_user_id,
                ClientModel.deleted_at.is_(None),
            )
        )

    async def get_deal_by_id(self, deal_id: uuid.UUID, owner_user_id: uuid.UUID):
        return await self.db.scalar(
            select(DealModel).where(
                DealModel.id == deal_id,
                DealModel.owner_user_id == owner_user_id,
                DealModel.deleted_at.is_(None),
            )
        )

    async def get_contract_by_id(self, contract_id: uuid.UUID, owner_user_id: uuid.UUID):
        return await self.db.scalar(
            select(ContractModel).where(
                ContractModel.id == contract_id, ContractModel.owner_user_id == owner_user_id
            )
        )

    async def add_line_item(self, **values):
        item = InvoiceLineItemModel(**values)
        self.db.add(item)
        await self.db.flush()
        return item

    async def replace_line_items(self, invoice_id: uuid.UUID, items: list) -> None:
        await self.db.execute(
            delete(InvoiceLineItemModel).where(InvoiceLineItemModel.invoice_id == invoice_id)
        )
        for item in items:
            self.db.add(
                InvoiceLineItemModel(
                    invoice_id=invoice_id,
                    description=item.description,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    amount=item.quantity * item.unit_price,
                    sort_order=item.sort_order,
                )
            )
        await self.db.flush()

    async def list_all(
        self, owner_user_id: uuid.UUID, status: str | None = None, invoice_number: str | None = None
    ) -> list:
        conditions = [InvoiceModel.owner_user_id == owner_user_id]
        if status is not None:
            conditions.append(InvoiceModel.status == status)
        if invoice_number is not None:
            conditions.append(InvoiceModel.invoice_number.ilike(f"%{invoice_number}%"))
        result = await self.db.execute(select(InvoiceModel).where(*conditions))
        return list(result.scalars().all())

    async def add_payment(self, **values):
        payment = InvoicePaymentRecordModel(**values)
        self.db.add(payment)
        await self.db.flush()
        return payment

    async def list_payments(self, invoice_id: uuid.UUID) -> list:
        result = await self.db.execute(
            select(InvoicePaymentRecordModel)
            .where(InvoicePaymentRecordModel.invoice_id == invoice_id)
            .order_by(InvoicePaymentRecordModel.payment_date, InvoicePaymentRecordModel.created_at)
        )
        return list(result.scalars().all())

    async def save(self, obj):
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def delete(self, obj) -> None:
        await self.db.delete(obj)
        await self.db.flush()
