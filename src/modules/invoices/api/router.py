"""Invoices API router."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.invoices.application.service import InvoicesService
from src.modules.invoices.schemas.request import InvoiceRequest
from src.modules.invoices.schemas.response import InvoiceResponse
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
) -> ApiResponse[list[InvoiceResponse]]:
    invoices = await InvoicesService(db=db).list_all(user_id)
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
    payload: InvoiceRequest,
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
