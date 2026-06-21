"""Contracts API api."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.contracts.application.service import ContractsService
from src.modules.contracts.schemas.request import ContractRequest
from src.modules.contracts.schemas.response import ContractResponse
from src.shared.dependencies.auth import CurrentUserId
from src.shared.responses.response import ApiResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


class MsgResp(BaseModel):
    detail: str


@router.post("", response_model=ApiResponse[ContractResponse], status_code=201)
async def create_contract(
    payload: ContractRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ContractResponse]:
    contract = await ContractsService(db=db).create(user_id, payload)
    return ApiResponse.created(ContractResponse.model_validate(contract))


@router.get("", response_model=ApiResponse[list[ContractResponse]])
async def list_contracts(
    user_id: CurrentUserId,
    db: DBSession,
    status: str | None = Query(default=None, description="Filter by status: draft, pending_signatures, active, completed, terminated"),
) -> ApiResponse[list[ContractResponse]]:
    contracts = await ContractsService(db=db).list_all(user_id, status=status)
    return ApiResponse.ok([ContractResponse.model_validate(c) for c in contracts])


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


@router.delete("/{contract_id}", response_model=ApiResponse[MsgResp])
async def delete_contract(
    contract_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[MsgResp]:
    await ContractsService(db=db).delete(user_id, contract_id)
    return ApiResponse.ok(MsgResp(detail="Contract deleted"))
