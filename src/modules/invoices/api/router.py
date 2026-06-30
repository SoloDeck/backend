"""Invoices API api."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.invoices.application.service import InvoicesService
from src.modules.invoices.schemas.request import (
    InvoiceRequest,
    InvoiceUpdateRequest,
    PaymentRequest,
)
from src.modules.invoices.schemas.response import InvoiceResponse, PaymentRecordResponse
from src.shared.dependencies.auth import CurrentUserId
from src.shared.responses.response import ApiResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


class MsgResp(BaseModel):
    detail: str


@router.post("", response_model=ApiResponse[InvoiceResponse], status_code=201)
async def create_invoice(
    payload: InvoiceRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[InvoiceResponse]:
    invoice = await InvoicesService(db=db).create(user_id, payload)
    return ApiResponse.created(InvoiceResponse.model_validate(invoice))


@router.get("", response_model=ApiResponse[list[InvoiceResponse]])
async def list_invoices(
    user_id: CurrentUserId,
    db: DBSession,
    status: str | None = Query(
        default=None, description="Filter by status: draft, sent, paid, overdue, cancelled"
    ),
    invoice_number: str | None = Query(
        default=None, description="Search by invoice number (partial match)"
    ),
) -> ApiResponse[list[InvoiceResponse]]:
    invoices = await InvoicesService(db=db).list_all(
        user_id, status=status, invoice_number=invoice_number
    )
    return ApiResponse.ok([InvoiceResponse.model_validate(i) for i in invoices])


@router.get("/{invoice_id}", response_model=ApiResponse[InvoiceResponse])
async def get_invoice(
    invoice_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[InvoiceResponse]:
    invoice = await InvoicesService(db=db).get_one(user_id, invoice_id)
    return ApiResponse.ok(InvoiceResponse.model_validate(invoice))


@router.patch("/{invoice_id}", response_model=ApiResponse[InvoiceResponse])
async def update_invoice(
    invoice_id: uuid.UUID,
    payload: InvoiceUpdateRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[InvoiceResponse]:
    invoice = await InvoicesService(db=db).update(user_id, invoice_id, payload)
    return ApiResponse.ok(InvoiceResponse.model_validate(invoice))


@router.delete("/{invoice_id}", response_model=ApiResponse[MsgResp])
async def delete_invoice(
    invoice_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[MsgResp]:
    await InvoicesService(db=db).delete(user_id, invoice_id)
    return ApiResponse.ok(MsgResp(detail="Invoice deleted"))


@router.post("/{invoice_id}/send", response_model=ApiResponse[InvoiceResponse])
async def send_invoice(
    invoice_id: uuid.UUID, user_id: CurrentUserId, db: DBSession
) -> ApiResponse[InvoiceResponse]:
    invoice = await InvoicesService(db=db).send(user_id, invoice_id)
    return ApiResponse.ok(InvoiceResponse.model_validate(invoice))


@router.post("/{invoice_id}/void", response_model=ApiResponse[InvoiceResponse])
async def void_invoice(
    invoice_id: uuid.UUID, user_id: CurrentUserId, db: DBSession
) -> ApiResponse[InvoiceResponse]:
    invoice = await InvoicesService(db=db).void(user_id, invoice_id)
    return ApiResponse.ok(InvoiceResponse.model_validate(invoice))


@router.post(
    "/{invoice_id}/payments",
    response_model=ApiResponse[InvoiceResponse],
    status_code=status.HTTP_201_CREATED,
)
async def record_payment(
    invoice_id: uuid.UUID, payload: PaymentRequest, user_id: CurrentUserId, db: DBSession
) -> ApiResponse[InvoiceResponse]:
    invoice = await InvoicesService(db=db).record_payment(user_id, invoice_id, payload)
    return ApiResponse.created(InvoiceResponse.model_validate(invoice))


@router.get("/{invoice_id}/payments", response_model=ApiResponse[list[PaymentRecordResponse]])
async def list_payments(
    invoice_id: uuid.UUID, user_id: CurrentUserId, db: DBSession
) -> ApiResponse[list[PaymentRecordResponse]]:
    payments = await InvoicesService(db=db).list_payments(user_id, invoice_id)
    return ApiResponse.ok([PaymentRecordResponse.model_validate(p) for p in payments])
