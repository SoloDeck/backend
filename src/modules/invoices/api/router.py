"""Invoices API api."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.invoices.application.service import InvoicesService
from src.modules.invoices.domain.value_objects.invoice_status import InvoiceStatus
from src.modules.invoices.schemas.request import (
    InvoiceRequest,
    InvoiceUpdateRequest,
    PaymentRequest,
)
from src.modules.invoices.schemas.response import InvoiceResponse, PaymentRecordResponse
from src.shared.dependencies.auth import CurrentUserId
from src.shared.responses.response import ApiResponse, PaginatedResponse

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


@router.get("", response_model=PaginatedResponse[InvoiceResponse])
async def list_invoices(
    user_id: CurrentUserId,
    db: DBSession,
    status: InvoiceStatus | None = Query(
        default=None,
        description="Filter by status: draft, sent, partially_paid, paid, overdue, void",
    ),
    invoice_number: str | None = Query(
        default=None, description="Search by invoice number (partial match)"
    ),
    from_issue_date: date | None = Query(default=None),
    to_issue_date: date | None = Query(default=None),
    from_due_date: date | None = Query(default=None),
    to_due_date: date | None = Query(default=None),
    overdue_only: bool = Query(
        default=False,
        description="Only invoices past due_date with an outstanding balance",
    ),
    sort_by: Literal["issue_date", "due_date", "total", "created_at"] = Query(
        default="issue_date"
    ),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[InvoiceResponse]:
    invoices, total = await InvoicesService(db=db).list_all(
        user_id,
        status=status,
        invoice_number=invoice_number,
        from_issue_date=from_issue_date,
        to_issue_date=to_issue_date,
        from_due_date=from_due_date,
        to_due_date=to_due_date,
        overdue_only=overdue_only,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse.ok(
        [InvoiceResponse.model_validate(i) for i in invoices],
        total=total,
        page=page,
        page_size=page_size,
    )


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
