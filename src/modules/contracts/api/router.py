"""Contracts API router."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.contracts.application.service import ContractsService
from src.modules.contracts.schemas.request import ContractRequest, ContractStatusRequest
from src.modules.contracts.schemas.response import ContractExportResponse, ContractResponse
from src.shared.dependencies.auth import CurrentUserId
from src.shared.responses.response import ApiResponse, PaginatedResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


class MsgResp(BaseModel):
    detail: str


@router.get("", response_model=PaginatedResponse[ContractResponse])
async def list_contracts(
    user_id: CurrentUserId,
    db: DBSession,
    status: str | None = Query(
        default=None,
        description="Filter by status: draft, pending_signatures, active, completed, terminated, expired",
    ),
    deal_id: uuid.UUID | None = Query(default=None, description="Filter by deal"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[ContractResponse]:
    contracts, total = await ContractsService(db=db).list_all(
        user_id, status=status, deal_id=deal_id, page=page, page_size=page_size
    )
    return PaginatedResponse.ok(
        [ContractResponse.model_validate(c) for c in contracts],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=ApiResponse[ContractResponse], status_code=201)
async def create_contract(
    payload: ContractRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ContractResponse]:
    contract = await ContractsService(db=db).create(user_id, payload)
    return ApiResponse.created(ContractResponse.model_validate(contract))


@router.get("/{contract_id}", response_model=ApiResponse[ContractResponse])
async def get_contract(
    contract_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ContractResponse]:
    contract = await ContractsService(db=db).get_one(user_id, contract_id)
    return ApiResponse.ok(ContractResponse.model_validate(contract))


@router.patch("/{contract_id}", response_model=ApiResponse[ContractResponse])
async def update_contract(
    contract_id: uuid.UUID,
    payload: ContractRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ContractResponse]:
    contract = await ContractsService(db=db).update(user_id, contract_id, payload)
    return ApiResponse.ok(ContractResponse.model_validate(contract))


@router.patch("/{contract_id}/status", response_model=ApiResponse[ContractResponse])
async def transition_contract_status(
    contract_id: uuid.UUID,
    payload: ContractStatusRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ContractResponse]:
    contract = await ContractsService(db=db).transition_status(user_id, contract_id, payload.status)
    return ApiResponse.ok(ContractResponse.model_validate(contract))


@router.get("/{contract_id}/export", response_model=ApiResponse[ContractExportResponse])
async def export_contract_pdf(
    contract_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ContractExportResponse]:
    result = await ContractsService(db=db).export_pdf(user_id, contract_id)
    return ApiResponse.ok(ContractExportResponse(**result))


@router.delete("/{contract_id}", response_model=ApiResponse[MsgResp])
async def delete_contract(
    contract_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[MsgResp]:
    await ContractsService(db=db).delete(user_id, contract_id)
    return ApiResponse.ok(MsgResp(detail="Contract deleted"))