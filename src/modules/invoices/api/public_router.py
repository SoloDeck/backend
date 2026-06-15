"""Public invoice endpoints — no authentication required."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.invoices.application.service import InvoicesService
from src.modules.invoices.schemas.response import InvoiceResponse
from src.shared.responses.response import ApiResponse

router = APIRouter()
DBSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/{share_token}", response_model=ApiResponse[InvoiceResponse])
async def get_public_invoice(share_token: str, db: DBSession) -> ApiResponse[InvoiceResponse]:
    invoice = await InvoicesService(db=db).get_public_view(share_token)
    return ApiResponse.ok(InvoiceResponse.model_validate(invoice))
