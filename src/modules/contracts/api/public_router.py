"""Public contract endpoints — no authentication required."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.contracts.application.service import ContractsService
from src.modules.contracts.schemas.request import ClientSignRequest
from src.modules.contracts.schemas.response import PublicContractResponse
from src.shared.responses.response import ApiResponse

router = APIRouter()
DBSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/{share_token}", response_model=ApiResponse[PublicContractResponse])
async def get_public_contract(
    share_token: str, db: DBSession
) -> ApiResponse[PublicContractResponse]:
    contract = await ContractsService(db=db).get_public_view(share_token)
    return ApiResponse.ok(PublicContractResponse.model_validate(contract))


@router.post("/{share_token}/sign", response_model=ApiResponse[PublicContractResponse])
async def sign_contract_via_link(
    share_token: str, payload: ClientSignRequest, db: DBSession
) -> ApiResponse[PublicContractResponse]:
    contract = await ContractsService(db=db).sign_via_share_token(
        share_token, payload.signer_name
    )
    return ApiResponse.ok(PublicContractResponse.model_validate(contract))
